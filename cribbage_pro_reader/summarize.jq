[
  foreach .[] as $row 
  (
    {
      win_streak: 0,
      lose_streak: 0
    };

    ($row.rounds[-1].score > $row.rounds[-1].opponent_score) as $won
    |
    if $won then
      .win_streak += 1
      | .lose_streak = 0
    else
      .win_streak = 0
      | .lose_streak += 1
    end;

    $row + {
      win_streak,
      lose_streak
    }
  ) 
  | {
    opponent: .opponent_name, 
    score: .rounds[-1].score, 
    opponent_score: .rounds[-1].opponent_score, 
    win_streak: .win_streak, 
    lose_streak: .lose_streak,
    rounds: .rounds | length
  }
]
