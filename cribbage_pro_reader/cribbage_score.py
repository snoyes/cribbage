from pprint import pprint
import itertools
from collections import Counter

def powerset(s):
    s = list(s)
    return itertools.chain.from_iterable(itertools.combinations(s, r) for r in range(len(s)+1))

def parse_card(card):
    card = card.strip().upper()
    suit = card[-1]
    rank_text = card[:-1]

    rank_map = {"A": 1, "J": 11, "Q": 12, "K": 13}
    rank = int(rank_map.get(rank_text, rank_text))

    return rank, suit

def rank(card):
    return parse_card(card)[0]

def peg_value(card):
    return min(rank(card), 10)

def score_pairs(sequence):
    r = rank(sequence[-1])

    count = 1
    i = len(sequence) - 2

    while i >= 0 and rank(sequence[i]) == r:
        count += 1
        i -= 1

    if count == 2:
        return 2, "pair"
    if count == 3:
        return 6, "three of a kind"
    if count == 4:
        return 12, "four of a kind"
    return 0, None

def score_runs(sequence):
    """
    Returns (points, description) for longest run ending at last card.
    """
    for n in range(len(sequence), 2, -1):
        tail = sequence[-n:]
        ranks = [rank(c) for c in tail]

        if len(set(ranks)) != n:
            continue

        if max(ranks) - min(ranks) == n - 1:
            return n, f"run of {n}"

    return 0, None

def can_play_any(cards, count):
    limit = 31 - count
    return any(peg_value(c) <= limit for c in cards)

def score_pegging(dealer_hand, pone_hand, plays):

    dealer_remaining = list(dealer_hand)
    pone_remaining = list(pone_hand)


    count = 0
    sequence = []

    dealer_go = False
    pone_go = False

    results = []

    last_player = None
    last_sequence_already_scored = False

    for card in plays:

        if card in dealer_remaining:
            player = "dealer"
            dealer_remaining.remove(card)
        elif card in pone_remaining:
            player = "pone"
            pone_remaining.remove(card)
        else:
            raise ValueError(f"Card {card} not found in either hand")

        value = peg_value(card)

        #
        # New sequence begins because previous one ended.
        #
        if count + value > 31:

            if (
                count != 31
                and last_player is not None
                and not last_sequence_already_scored
            ):
                results.append({
                    "player": last_player,
                    "card": None,
                    "points": 1,
                    "events": ["sequence end"]
                })

            count = 0
            sequence = []

            dealer_go = False
            pone_go = False
            last_sequence_already_scored = False

        count += value
        sequence.append(card)

        points = 0
        events = []

        if count == 15:
            points += 2
            events.append("15")

        pair_points, pair_desc = score_pairs(sequence)
        if pair_points:
            points += pair_points
            events.append(pair_desc)

        run_points, run_desc = score_runs(sequence)
        if run_points:
            points += run_points
            events.append(run_desc)

        if count == 31:
            points += 2
            events.append("31")

        results.append({
            "player": player,
            "card": card,
            "count": count,
            "points": points,
            "events": events
        })

        last_player = player

        dealer_can = can_play_any(dealer_remaining, count)
        pone_can = can_play_any(pone_remaining, count)

        if not dealer_can:
            dealer_go = True

        if not pone_can:
            pone_go = True

        #
        # 31 ends the sequence immediately.
        #
        if count == 31:
            count = 0
            sequence = []

            dealer_go = False
            pone_go = False

            last_sequence_already_scored = True
            continue

        #
        # Sequence ends only when neither side can play.
        #
        if dealer_go and pone_go:

            results.append({
                "player": last_player,
                "card": None,
                "points": 1,
                "events": ["sequence end"]
            })

            last_sequence_already_scored = True

            count = 0
            sequence = []

            dealer_go = False
            pone_go = False

    #
    # Final sequence.
    #
    if (
        results
        and not last_sequence_already_scored
    ):
        last_play = next(
            r for r in reversed(results)
            if r["card"] is not None
        )

        if "31" not in last_play["events"] and not dealer_remaining and not pone_remaining:
            results.append({
                "player": last_play["player"],
                "card": None,
                "points": 1,
                "events": ["sequence end"]
            })

    return results

def calc_hand_score(hand, startCard, isCrib=False):
    #print(f'{hand=} {startCard=} {isCrib=}')
    cards = tuple(hand) + (startCard,)

    fifteens = 2 * sum(sum(p) == 15 for p in powerset(map(peg_value, cards)))
    #print(f'15 for {fifteens}')

    pairs = 2 * sum(a == b for a, b in itertools.combinations(map(rank, cards), 2))
    #print(f'Pairs for {pairs}')

    runs = 0
    for length in reversed(range(3, 6)):
        runs = length * sum((all(b-a == 1 for a, b in itertools.pairwise(sorted(takefour))) for takefour in itertools.combinations(map(rank, cards), length)))
        if runs:
            break
    #print(f'Runs for {runs}')

    all_suits = [card[-1] for card in cards]
    hand_suits = [card[-1] for card in hand]
    flush = 0
    if len(set(all_suits)) == 1:
        flush = 5
    elif len(set(hand_suits)) == 1 and not isCrib:
        flush = 4
    #print(f'Flush for {flush}')

    nobs = int(any(card[0] == 'J' and card[-1] == startCard[-1] for card in hand))
    #print(f'Nobs for {nobs}')

    total = fifteens + pairs + runs + flush + nobs
    #print(f'Total {total}')

    #print()
    return total

    
if __name__ == '__main__':
    for hand, startCard in (
        (('4H', '5H', '6H', 'JH'), 'AC'),
        (('AH', '2H', '3H', '3S'), '4C'),
        (('5H', '5C', '5S', 'JD'), '5D'),
        (('2H', '4C', '6S', '8D'), '10H'),
        (('5S', '5C', '10S', 'QD'), 'JC')
    ):
        result = calc_hand_score(hand, startCard, False)
        print(hand, startCard, result)

    """
    pegging = score_pegging(('AH', 'AD', 'AC', 'AS'), ('KH', 'KC', 'KD', 'KS'), ('KH', 'AH', 'KC', 'AC', 'AD', 'AS', 'KD', 'KS'))
    pprint(pegging)
    print()
    pegging = score_pegging(('5H', '7C', '9S', 'JS'), ('4H', '6C', '8D', '10D'), ('4H', '5H', '6C', '7C', '8D', '9S', '10D', 'JS'))
    pprint(pegging)
    print()
    pegging = score_pegging(('AH', 'AC', 'JS', 'JD'), ('KH', 'KC', 'KD', 'KS'), ('KH', 'JS', 'KC', 'AH', 'KD', 'JD', 'KS', 'AC'))
    pprint(pegging)
    print()
    pegging = score_pegging(('KH', 'KC', 'KD', 'KS'), ('AH', 'AC', 'JS', 'JD'), ('JS', 'KH', 'JD', 'AH', 'KD', 'AC', 'KC', 'KS'))
    pprint(pegging)
    print()
    pegging = score_pegging(('KH', 'KC', 'KD', 'KS'), ('AH', 'AC', '9S', 'JD'), ('9S', 'KH', 'JD', 'AH', 'KD', 'AC', 'KC', 'KS'))
    pprint(pegging)
    """
