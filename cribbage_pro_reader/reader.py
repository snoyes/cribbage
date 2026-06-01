from cribbage_score import calc_hand_score, score_pegging
from itertools import zip_longest
from pathlib import Path
from PIL import Image
import argparse
import cv2
import json
import numpy as np
import os
import pytesseract
import re
import sys
import zipfile
pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

def main():
    args = get_args()

    game = dict()

    files = filenames_from_zip(args.zip_file)
    game['file_source'] = args.zip_file
    game['rounds'] = list()
    game_round = {'HAND_REVIEW': [], 'OPPONENT_HAND_REVIEW': [], 'PEGGING_REVIEW': []}

    for filename, img in files:
        if 'opponent_name' not in game:
            opponent_name = get_opponent_name(img)
            game['opponent_name'] = opponent_name

        img.seek(0)
        screenshot_type = get_screenshot_type(img)
        if not screenshot_type:
            continue

        img.seek(0)
        cards = read_image(filename, img, args.anchor, args.debug_dir, args.templates_dir)

        for row in sorted(cards.keys()):
            sorted_cards = ({x: cards[row][x] for x in sorted(cards[row])})
            values = tuple(sorted_cards.values())
            if values not in game_round[screenshot_type]:
                game_round[screenshot_type].append(values)

    # Sometimes a full row of cards is not read when it's right at the top or bottom of the screen
    # Discard any such partial rows
    game_round['HAND_REVIEW'] = [row for row in game_round['HAND_REVIEW'] if len(row) == 7]
    game_round['OPPONENT_HAND_REVIEW'] = [row for row in game_round['OPPONENT_HAND_REVIEW'] if len(row) == 7]
    # The very last pegging run might be less than 8 cards if a score ended the game
    game_round['PEGGING_REVIEW'][:-1] = [row for row in game_round['PEGGING_REVIEW'][:-1] if len(row) == 8]

    if len(game_round['HAND_REVIEW']) not in (len(game_round['PEGGING_REVIEW']), len(game_round['PEGGING_REVIEW']) + 1):
        print('Cannot match hands to pegging', file=sys.stderr)
        print(game_round, file=sys.stderr)
        exit()

    game['rounds'] = assemble_rounds(game_round)
    
    json_file = Path(game['file_source']).with_suffix(".json")

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(game, f, indent=2)

def assemble_rounds(game_round):
    rounds = []
    score = opponent_score = 0
    for hand, opponent, pegging in zip_longest(game_round['HAND_REVIEW'], game_round['OPPONENT_HAND_REVIEW'], game_round['PEGGING_REVIEW'], fillvalue=()):
        if pegging:
            position = 'pone' if pegging[0] in hand else 'dealer'
        elif rounds:
            position = 'pone' if rounds[-1]['position'] == 'dealer' else 'dealer'
        else:
            position = 'unknown'

        heels = 2 * int(hand[6][0] == 'J')

        dealer_hand = hand[:4]
        pone_hand = opponent[:4]
        if position == 'pone':
            dealer_hand, pone_hand = pone_hand, dealer_hand
            opponent_score += heels
        else:
            score += heels

        pegging_score = score_pegging(dealer_hand, pone_hand, pegging)
        for play in pegging_score:
            if play['player'] == position:
                score += play['points']
            else:
                opponent_score += play['points']

        hand_score = calc_hand_score(hand[:4], hand[6], isCrib=False)
        opponent_hand_score = calc_hand_score(opponent[:4], opponent[6], isCrib=False)
        crib_score = calc_hand_score(hand[4:6] + opponent[4:6], hand[6], isCrib=True)

        if score < 121 and opponent_score < 121:
            if position == 'pone':
                score += hand_score
            else:
                opponent_score += opponent_hand_score

        if score < 121 and opponent_score < 121:
            if position == 'dealer':
                score += hand_score
            else:
                opponent_score += opponent_hand_score

        if score < 121 and opponent_score < 121:
            if position == 'dealer':
                score += crib_score
            else:
                opponent_score += crib_score

        score = min(121, score)
        opponent_score = min(121, opponent_score)

        rounds.append(
            {
                'round': len(rounds) + 1,
                'position': position,
                'hand': hand[:4],
                'discard': hand[4:6],
                'opponent_hand': opponent[:4],
                'opponent_discard': opponent[4:6],
                'start': hand[6],
                'heels': 2 * int(hand[6][0] == 'J'),
                'hand_score': hand_score,
                'opponent_hand_score': opponent_hand_score,
                'crib_score': crib_score,
                'pegging': pegging_score,
                'score': score,
                'opponent_score': opponent_score
            }
        )
    return rounds

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_file")
    parser.add_argument("--anchor", default="anchor.png")
    parser.add_argument("--templates_dir", default="templates")
    parser.add_argument("--debug_dir", default="debug_images")
    return parser.parse_args()

def filenames_from_zip(zip_file):
    with zipfile.ZipFile(zip_file, 'r') as archive:
        files = [
                f for f in archive.namelist() 
                if f.lower().endswith(('.png', '.jpg'))
        ]
        files.sort()
        for f in files:
            yield f, archive.open(f)

def read_image(filename, img, anchor, output_dir, templates):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    anchor = cv2.imread(anchor, cv2.IMREAD_GRAYSCALE)
    th, tw = anchor.shape
    
    card_templates = [
            {
                "label": os.path.splitext(f)[0], 
                "img": cv2.imread(os.path.join(templates, f))
            } 
            for f in os.listdir(templates) 
            if f.lower().endswith('.png')
    ]

    # Load your rank templates (The numbers/letters only)
    rank_templates = {
        os.path.splitext(f)[0][:-1]: cv2.imread(os.path.join("templates", f)) 
        for f in os.listdir("templates") 
        if f.endswith('.png')
    }

    # Load the Edge Anchors we created
    edge_anchors = {
        "heart": cv2.imread(os.path.join("edge_templates", "master_edge_heart.png"), 0),
        "diamond": cv2.imread(os.path.join("edge_templates", "master_edge_diamond.png"), 0),
        "club": cv2.imread(os.path.join("edge_templates", "master_edge_club.png"), 0),
        "spade": cv2.imread(os.path.join("edge_templates", "master_edge_spade.png"), 0)
    }

    X_MIN, X_MAX = 130, 480 + tw
    Y_MIN, Y_MAX = 370, 850 + th
    cards_detected = dict()

    img = cv2.imdecode(np.frombuffer(img.read(), np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    res = cv2.matchTemplate(gray, anchor, cv2.TM_CCOEFF_NORMED)
    pts = np.column_stack(np.where(res >= 0.35)[::-1])
    pts = pts[(pts[:, 0] >= X_MIN) & (pts[:, 0] + tw <= X_MAX) & 
              (pts[:, 1] >= Y_MIN) & (pts[:, 1] + th <= Y_MAX)]

    final_pts = []
    if len(pts) > 0:
        scores = res[pts[:, 1], pts[:, 0]]
        order = scores.argsort()[::-1]
        while order.size > 0:
            i = order[0]
            final_pts.append(pts[i])
            xx1 = np.maximum(pts[i, 0], pts[order[1:], 0])
            yy1 = np.maximum(pts[i, 1], pts[order[1:], 1])
            xx2 = np.minimum(pts[i, 0] + tw, pts[order[1:], 0] + tw)
            yy2 = np.minimum(pts[i, 1] + th, pts[order[1:], 1] + th)
            overlap = (np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)) / (tw * th)
            order = order[np.where(overlap < 0.3)[0] + 1]

    for pt in final_pts:
        detected_card_roi = img[pt[1]:pt[1]+th, pt[0]:pt[0]+tw]
        label, confidence = identify_card(detected_card_roi, rank_templates, edge_anchors)
        if confidence > 0.6:
            x = pt[0]
            y = pt[1]
            cv2.rectangle(img, (x, y), (x+tw, y+th), (0, 255, 0), 2)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            (text_width, text_height), _ = cv2.getTextSize(label, font, font_scale, 4)
            text_x = x + (tw - text_width) // 2
            text_y = y + (th + text_height) // 2
            cv2.putText(img, label, (text_x, text_y), font, font_scale, (0,0,0), 4, cv2.LINE_AA)
            cv2.putText(img, label, (text_x, text_y), font, font_scale, (255,255,255), 1, cv2.LINE_AA)

            row = min((y+dy for dy in range(-20, 21) if y+dy in cards_detected), default=y)
            if row not in cards_detected:
                cards_detected[row] = dict()
            cards_detected[row][int(pt[0])] = label

    cv2.imwrite(os.path.join(output_dir, f"{os.path.basename(filename)}"), img)
    return cards_detected

def identify_card(roi, rank_templates, edge_anchors):
    # 1. RANK IDENTIFICATION (Standard Template Matching)
    best_rank = "???"
    max_val = -1.0
    for label, t_img in rank_templates.items():
        res = cv2.matchTemplate(roi, t_img, cv2.TM_CCOEFF_NORMED)
        _, val, _, _ = cv2.minMaxLoc(res)
        if val > max_val:
            max_val = val
            best_rank = label

    # 2. SUIT IDENTIFICATION (Edge-Based Matching)
    h, w = roi.shape[:2]
    suit_roi = roi[int(h*0.55):int(h*0.95), int(w*0.05):int(w*0.55)]
    
    # Apply Canny to the card ROI to match our edge-anchors
    gray = cv2.cvtColor(suit_roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edges_resized = cv2.resize(edges, (50, 50))
    
    # Compare against our four Edge-Anchors
    best_suit = None
    max_suit_val = -1
    for suit, anchor in edge_anchors.items():
        res = cv2.matchTemplate(edges_resized, anchor, cv2.TM_CCOEFF_NORMED)
        _, val, _, _ = cv2.minMaxLoc(res)
        if val > max_suit_val:
            max_suit_val = val
            best_suit = suit
            
    # Return Rank + Suit
    suit_map = {'heart': 'H', 'diamond': 'D', 'club': 'C', 'spade': 'S'}
    return f"{best_rank}{suit_map[best_suit]}", max_val

def get_opponent_name(file_path):
    img = Image.open(file_path)
    text = pytesseract.image_to_string(img, config='--psm 6')
    
    # Regex pattern: 
    # Finds "against", "SKUNKED", or "SKUNKED by" 
    # Captures the name until a comma or exclamation point
    pattern = r"(?:against|SKUNKED(?: by)?)\s+([A-Za-z0-9_]+)[,!]"
    
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        return match.group(1)
    
    # Fallback: If OCR fails to capture the exact pattern, 
    # look at the diagonal area specifically
    return "Name not found"

def get_screenshot_type(img):
    img = cv2.imdecode(np.frombuffer(img.read(), np.uint8), cv2.IMREAD_GRAYSCALE)
    
    for anchor, screenshot_type in (
            ('opponent_hands_dealt.jpg', 'OPPONENT_HAND_REVIEW'),
            ('hands_dealt.jpg', 'HAND_REVIEW'),
            ('pegging_play.jpg', 'PEGGING_REVIEW'),
    ):
        template = cv2.imread(os.path.join("screenshot_type_templates", anchor), cv2.IMREAD_GRAYSCALE)
        res = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        
        if max_val >= 0.8:
            return screenshot_type

    return None

if __name__ == "__main__":
    main()
