from itertools import pairwise, zip_longest
import zipfile
import cv2
import numpy as np
import argparse
import os
import pytesseract
pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
from PIL import Image
import re
import json
import sys

pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
def get_text(imageFile):
    img = Image.open(imageFile)

    crop_box = (115, 0, 115+470, 0+38)
    cropped_img = img.crop(crop_box)
    text = pytesseract.image_to_string(cropped_img, config='--psm 7')
    if text and (match := re.search(r"(.*?) \(\d{1,}\)", text)):
        print('I think the opponent is named', match.group(1))
    
    crop_box = (61, 718, 61+426, 718+86)
    cropped_img = img.crop(crop_box)
    text = pytesseract.image_to_string(cropped_img, config='--psm 7')
    if "Your crib scores" in text:
        return "DEALER_CRIB"

    crop_box = (193, 46, 193+527, 46+73)
    cropped_img = img.crop(crop_box)
    text = pytesseract.image_to_string(cropped_img, config='--psm 7')
    if "Opponent's crib scores" in text:
        return "PONE_CRIB"

    header_crop_box = (134, 322, 134+451, 322+49) 
    header_cropped_img = img.crop(header_crop_box)
    header_text = pytesseract.image_to_string(header_cropped_img, config='--psm 7')
    if "Hands Dealt" in header_text:
        crop_box = (134, 373, 134+412, 373+543)
        cropped_img = img.crop(crop_box)
        text = pytesseract.image_to_string(cropped_img, config='--psm 6')
        rounds = re.findall(r"Round \d{1,2}", text)
        return "HAND_REVIEW"

    if "Pegging / Play" in header_text:
        crop_box = (134, 373, 134+412, 373+543)
        cropped_img = img.crop(crop_box)
        text = pytesseract.image_to_string(cropped_img, config='--psm 6')
        rounds = re.findall(r"Round \d{1,2}", text)
        return "PEGGING_REVIEW"

    if "Cards in Last Round" in header_text:
        return "LASTROUND"

    return "unknown screen type"

def read_cards(filename, img, image_type, anchor, output_dir, templates):
    match image_type:
        case "DEALER_CRIB":
            crop_box = (125, 842, 125+417, 842+154)
        case "PONE_CRIB":
            crop_box = (185, 106, 185+417, 106+154)
        case "HAND_REVIEW" | "PEGGING_REVIEW" | "LASTROUND":
            crop_box = (134, 373, 134+412, 373+543)

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
        "heart": cv2.imread("master_edge_heart.png", 0),
        "diamond": cv2.imread("master_edge_diamond.png", 0),
        "club": cv2.imread("master_edge_club.png", 0),
        "spade": cv2.imread("master_edge_spade.png", 0)
    }

    #X_MIN, X_MAX = 130, 480 + tw
    #Y_MIN, Y_MAX = 370, 850 + th
    X_MIN, X_MAX = crop_box[0], crop_box[2]
    Y_MIN, Y_MAX = crop_box[1], crop_box[3]
    cards_detected = dict()

    img = cv2.imdecode(np.frombuffer(img.read(), np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    res = cv2.matchTemplate(gray, anchor, cv2.TM_CCOEFF_NORMED)
    pts = np.column_stack(np.where(res >= 0.35)[::-1])
    #pts = pts[(pts[:, 0] >= X_MIN) & (pts[:, 0] + tw <= X_MAX) & 
    #          (pts[:, 1] >= Y_MIN) & (pts[:, 1] + th <= Y_MAX)]

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

            row = pt[1]
            row = min((row+x for x in range(-30, 31) if row+x in cards_detected), default=row)
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

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_file")
    parser.add_argument("--anchor", default="ideal_anchor.png")
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

def main():
    args = get_args()

    for filename, img in filenames_from_zip(args.zip_file):
        image_type = get_text(img)
        img.seek(0)
        print(filename, image_type)
        cards = read_cards(filename, img, image_type, args.anchor, args.debug_dir, args.templates_dir)
        print(cards)
        print()

if __name__ == "__main__":
    main()
