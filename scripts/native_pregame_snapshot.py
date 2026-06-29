from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_core import NativeBattleSetup, NativeCore, build_native_core


def _deck_summary(path: Path, cards: tuple[int, ...]) -> dict[str, Any]:
    canonical = "".join(f"{card_id}\n" for card_id in cards).encode("ascii")
    return {
        "path": str(path.resolve()),
        "count": len(cards),
        "sha256": hashlib.sha256(canonical).hexdigest().upper(),
    }


def _player_counts(setup: NativeBattleSetup, *, include_setup_details: bool = False) -> list[dict[str, Any]]:
    players = [
        {
            "deck_count": player.deck_count,
            "hand_count": player.hand_count,
            "prize_count": player.prize_count,
        }
        for player in setup.players
    ]
    if include_setup_details:
        for index, player in enumerate(setup.players):
            players[index]["active_card_id"] = player.active_card_id
            players[index]["bench_count"] = len(player.bench_card_ids)
            players[index]["setup_complete"] = player.setup_complete
    return players


def _setup_summary(setup: NativeBattleSetup, *, seed: int, include_setup_details: bool = False) -> dict[str, Any]:
    return {
        "seed": seed,
        "turn": setup.turn,
        "first_player": setup.first_player if setup.first_player >= 0 else None,
        "current_player": setup.current_player,
        "mulligans": list(setup.setup_mulligans),
        "mulligan_draw_choices": list(setup.setup_mulligan_draw_choices),
        "players": _player_counts(setup, include_setup_details=include_setup_details),
    }


def _empty_visible_player(player_index: int, *, deck_count: int, hand_count: int, hide_hand: bool) -> dict[str, Any]:
    return {
        "active": [],
        "bench": [],
        "benchMax": 5,
        "deckCount": deck_count,
        "discard": [],
        "prize": [],
        "handCount": hand_count,
        "hand": None if hide_hand else [],
        "poisoned": False,
        "burned": False,
        "asleep": False,
        "paralyzed": False,
        "confused": False,
        "playerIndex": player_index,
    }


def _pregame_observation(setup: NativeBattleSetup) -> dict[str, Any]:
    return {
        "select": {
            "context": 41,
            "type": 9,
            "minCount": 1,
            "maxCount": 1,
            "option": [{"type": 1}, {"type": 2}],
        },
        "logs": [],
        "current": {
            "turn": 0,
            "turnActionCount": 1,
            "yourIndex": 0,
            "firstPlayer": None,
            "supporterPlayed": False,
            "lunarCycleUsed": False,
            "fightingAttackBonus": 0,
            "stadiumPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "result": -1,
            "stadium": [],
            "looking": None,
            "players": [
                _empty_visible_player(
                    0,
                    deck_count=setup.players[0].deck_count,
                    hand_count=setup.players[0].hand_count,
                    hide_hand=False,
                ),
                _empty_visible_player(
                    1,
                    deck_count=setup.players[1].deck_count,
                    hand_count=setup.players[1].hand_count,
                    hide_hand=True,
                ),
            ],
        },
        "search_begin_input": None,
    }


def _pregame_visualizer_frame(setup: NativeBattleSetup) -> dict[str, Any]:
    frame = _pregame_observation(setup)
    frame["select"] = {
        "context": "IsFirst",
        "type": "YesNo",
        "minCount": 1,
        "maxCount": 1,
        "option": [{"type": "Yes"}, {"type": "No"}],
    }
    frame["current"]["players"] = [
        _empty_visible_player(
            0,
            deck_count=setup.players[0].deck_count,
            hand_count=setup.players[0].hand_count,
            hide_hand=False,
        ),
        _empty_visible_player(
            1,
            deck_count=setup.players[1].deck_count,
            hand_count=setup.players[1].hand_count,
            hide_hand=False,
        ),
    ]
    return frame


def _visible_player(setup: NativeBattleSetup, core: NativeCore, player_index: int) -> dict[str, Any]:
    return setup.players[player_index].to_observation_player(
        viewer_index=player_index,
        player_index=player_index,
        current_turn=setup.turn,
        stadium_card_id=setup.stadium_card_id,
        native_core=core,
    )


def _visualizer_setup_active_frame(
    setup: NativeBattleSetup,
    core: NativeCore,
    *,
    acting_player: int,
    turn_action_count: int,
) -> dict[str, Any]:
    observation = setup.to_observation(player_index=acting_player, native_core=core)
    current = dict(observation["current"])
    current["turnActionCount"] = turn_action_count
    current["players"] = [
        _visible_player(setup, core, 0),
        _visible_player(setup, core, 1),
    ]
    select = dict(observation["select"])
    raw_context = select.get("context")
    select["context"] = {
        0: "Main",
        1: "SetupActivePokemon",
        2: "SetupBenchPokemon",
    }.get(raw_context, raw_context)
    select["type"] = "Card" if raw_context in {1, 2} else {0: "Action", 1: "Card"}.get(
        select.get("type"),
        select.get("type"),
    )
    if raw_context in {1, 2}:
        select["option"] = [
            {
                **option,
                "type": "Card",
            }
            for option in observation["select"]["option"]
        ]
    else:
        select["option"] = [dict(option) for option in observation["select"]["option"]]
    return {
        "select": select,
        "logs": [dict(item) for item in setup.logs],
        "current": current,
        "search_begin_input": None,
    }


def _setup_active_option(setup: NativeBattleSetup, core: NativeCore, *, player_index: int, option_index: int) -> dict:
    observation = setup.to_observation(player_index=player_index, native_core=core)
    options = observation["select"]["option"]
    if option_index < 0 or option_index >= len(options):
        raise ValueError(
            f"setup active option index {option_index} is outside available options for player {player_index}: "
            f"{len(options)}"
        )
    return options[option_index]


def _setup_option(
    setup: NativeBattleSetup,
    core: NativeCore,
    *,
    player_index: int,
    option_index: int,
    label: str,
) -> dict:
    observation = setup.to_observation(player_index=player_index, native_core=core)
    options = observation["select"]["option"]
    if option_index < 0 or option_index >= len(options):
        raise ValueError(
            f"{label} option index {option_index} is outside available options for player {player_index}: "
            f"{len(options)}"
        )
    return options[option_index]


def _setup_options(
    setup: NativeBattleSetup,
    core: NativeCore,
    *,
    player_index: int,
    option_indexes: list[int],
    label: str,
) -> list[dict[str, Any]]:
    if len(set(option_indexes)) != len(option_indexes):
        raise ValueError(f"{label} option indexes must not contain duplicates")
    return [
        _setup_option(
            setup,
            core,
            player_index=player_index,
            option_index=option_index,
            label=label,
        )
        for option_index in option_indexes
    ]


def _apply_setup_bench_choices(
    setup: NativeBattleSetup,
    core: NativeCore,
    *,
    player_index: int,
    option_indexes: list[int],
    selected_options: list[dict[str, Any]],
) -> tuple[NativeBattleSetup, list[dict[str, Any]]]:
    removed_original_hand_indexes: list[int] = []
    applied: list[dict[str, Any]] = []
    for option_index, selected_option in zip(option_indexes, selected_options):
        original_hand_index = int(selected_option["index"])
        applied_hand_index = original_hand_index - sum(
            1 for removed in removed_original_hand_indexes if removed < original_hand_index
        )
        setup = core.select_setup_bench(
            setup,
            player_index=player_index,
            hand_index=applied_hand_index,
        )
        removed_original_hand_indexes.append(original_hand_index)
        applied.append(
            {
                "player_index": player_index,
                "option_index": option_index,
                "original_hand_index": original_hand_index,
                "applied_hand_index": applied_hand_index,
                "card_id": int(selected_option["cardId"]) if "cardId" in selected_option else None,
            }
        )
    setup = core.finish_setup_player(setup, player_index=player_index)
    return setup, applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a clean-room native pregame snapshot.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--first-player", type=int, choices=(0, 1), default=None)
    parser.add_argument("--setup-active-option-index", type=int, default=None)
    parser.add_argument("--next-setup-active-option-index", type=int, default=None)
    parser.add_argument("--setup-bench-option-index", type=int, action="append", default=[])
    parser.add_argument("--next-setup-bench-option-index", type=int, action="append", default=[])
    parser.add_argument("--draw-count-choice", type=int, action="append", default=[])
    parser.add_argument("--finish-setup-bench", action="store_true")
    parser.add_argument("--finish-next-setup-bench", action="store_true")
    parser.add_argument("--begin-first-turn", action="store_true")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--build-dir", type=Path, default=Path("artifacts/native_api"))
    args = parser.parse_args(argv)

    library_path = build_native_core(build_dir=args.build_dir)
    core = NativeCore(library_path)
    opponent_deck = args.opponent_deck or args.deck
    pregame = core.start_battle_pregame(args.deck, opponent_deck)
    player_deck = core.load_deck_csv(args.deck)
    opponent_loaded_deck = core.load_deck_csv(opponent_deck)

    if args.first_player is None:
        if (
            args.setup_active_option_index is not None
            or args.next_setup_active_option_index is not None
            or args.setup_bench_option_index
            or args.next_setup_bench_option_index
            or args.finish_setup_bench
            or args.finish_next_setup_bench
            or args.begin_first_turn
        ):
            raise ValueError(
                "--setup-active-option-index, --next-setup-active-option-index, --setup-bench-option-index, "
                "--next-setup-bench-option-index, and --begin-first-turn require --first-player"
            )
        payload = {
            "source": "clean-room native pregame",
            "library": str(library_path),
            "decks": {
                "player": _deck_summary(args.deck, player_deck.cards),
                "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
            },
            "native": {
                "phase": "pre_setup_is_first",
                "setup": _setup_summary(pregame, seed=args.seed),
            },
            "observation": _pregame_observation(pregame),
            "visualizer": {
                "frame_count": 1,
                "frames": [_pregame_visualizer_frame(pregame)],
                "truncated": False,
            },
            "kaggle_submission_made": False,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0

    setup = core.select_pregame_first_player(
        pregame,
        first_player=args.first_player,
        seed=args.seed,
    )
    observation = setup.to_observation(player_index=args.first_player, native_core=core)
    observation["current"]["turnActionCount"] = 2
    post_isfirst_frame = _visualizer_setup_active_frame(
        setup,
        core,
        acting_player=args.first_player,
        turn_action_count=2,
    )
    if args.setup_active_option_index is None and args.next_setup_active_option_index is not None:
        raise ValueError("--next-setup-active-option-index requires --setup-active-option-index")
    if (args.setup_bench_option_index or args.finish_setup_bench) and args.next_setup_active_option_index is None:
        raise ValueError("--setup-bench-option-index requires --next-setup-active-option-index")
    if (args.next_setup_bench_option_index or args.finish_next_setup_bench) and not (
        args.setup_bench_option_index or args.finish_setup_bench
    ):
        raise ValueError("--next-setup-bench-option-index requires --setup-bench-option-index")
    if args.begin_first_turn and not (args.next_setup_bench_option_index or args.finish_next_setup_bench):
        raise ValueError("--begin-first-turn requires --next-setup-bench-option-index")
    if args.setup_active_option_index is not None:
        selected_option = _setup_active_option(
            setup,
            core,
            player_index=args.first_player,
            option_index=args.setup_active_option_index,
        )
        setup = core.select_setup_active(
            setup,
            player_index=args.first_player,
            hand_index=int(selected_option["index"]),
        )
        next_player = 1 - args.first_player
        next_player_frame = _visualizer_setup_active_frame(
            setup,
            core,
            acting_player=next_player,
            turn_action_count=3,
        )
        if args.next_setup_active_option_index is not None:
            next_selected_option = _setup_active_option(
                setup,
                core,
                player_index=next_player,
                option_index=args.next_setup_active_option_index,
            )
            setup = core.select_setup_active(
                setup,
                player_index=next_player,
                hand_index=int(next_selected_option["index"]),
            )
            setup = core.deal_setup_prizes(setup)
            observation = setup.to_observation(player_index=args.first_player, native_core=core)
            observation["current"]["turnActionCount"] = 4
            post_both_actives_frame = _visualizer_setup_active_frame(
                setup,
                core,
                acting_player=args.first_player,
                turn_action_count=4,
            )
            setup_progress_frames = [
                _pregame_visualizer_frame(pregame),
                post_isfirst_frame,
                next_player_frame,
                post_both_actives_frame,
            ]
            draw_count_selections: list[dict[str, int]] = []
            draw_count_player = setup.pending_draw_count_player()
            if draw_count_player is not None:
                observation = setup.to_observation(player_index=draw_count_player, native_core=core)
                observation["current"]["turnActionCount"] = 4
                draw_count_frame = _visualizer_setup_active_frame(
                    setup,
                    core,
                    acting_player=draw_count_player,
                    turn_action_count=4,
                )
                draw_count_max = max(
                    0,
                    setup.setup_mulligans[1 - draw_count_player] - setup.setup_mulligans[draw_count_player],
                )
                if not args.draw_count_choice:
                    if args.setup_bench_option_index or args.finish_setup_bench:
                        raise ValueError(
                            "--setup-bench-option-index requires --draw-count-choice while DrawCount is pending"
                        )
                    payload = {
                        "source": "clean-room native pregame",
                        "library": str(library_path),
                        "decks": {
                            "player": _deck_summary(args.deck, player_deck.cards),
                            "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
                        },
                        "native": {
                            "phase": "post_both_setup_actives_draw_count",
                            "setup": _setup_summary(setup, seed=args.seed, include_setup_details=True),
                            "active_selections": [
                                {
                                    "player_index": args.first_player,
                                    "option_index": args.setup_active_option_index,
                                    "hand_index": int(selected_option["index"]),
                                    "card_id": int(selected_option["cardId"]) if "cardId" in selected_option else None,
                                },
                                {
                                    "player_index": next_player,
                                    "option_index": args.next_setup_active_option_index,
                                    "hand_index": int(next_selected_option["index"]),
                                    "card_id": int(next_selected_option["cardId"])
                                    if "cardId" in next_selected_option
                                    else None,
                                },
                            ],
                            "draw_count": {
                                "player_index": draw_count_player,
                                "source_mulligan_player_index": 1 - draw_count_player,
                                "max_count": draw_count_max,
                            },
                        },
                        "observation": observation,
                        "visualizer": {
                            "frame_count": 4,
                            "frames": [
                                _pregame_visualizer_frame(pregame),
                                post_isfirst_frame,
                                next_player_frame,
                                draw_count_frame,
                            ],
                            "truncated": False,
                        },
                        "kaggle_submission_made": False,
                    }
                    print(json.dumps(payload, sort_keys=True))
                    return 0
                setup_progress_frames = [
                    _pregame_visualizer_frame(pregame),
                    post_isfirst_frame,
                    next_player_frame,
                    draw_count_frame,
                ]
                for draw_count_choice in args.draw_count_choice:
                    pending_player = setup.pending_draw_count_player()
                    if pending_player is None:
                        raise ValueError("no mulligan DrawCount prompt is pending")
                    max_count = max(
                        0,
                        setup.setup_mulligans[1 - pending_player] - setup.setup_mulligans[pending_player],
                    )
                    setup = core.apply_pregame_draw_count(
                        setup,
                        player_index=pending_player,
                        count=draw_count_choice,
                    )
                    draw_count_selections.append(
                        {
                            "player_index": pending_player,
                            "count": draw_count_choice,
                            "max_count": max_count,
                        }
                    )
                observation = setup.to_observation(player_index=args.first_player, native_core=core)
                observation["current"]["turnActionCount"] = 5
                post_draw_count_frame = _visualizer_setup_active_frame(
                    setup,
                    core,
                    acting_player=args.first_player,
                    turn_action_count=5,
                )
                setup_progress_frames.append(post_draw_count_frame)
                if not (args.setup_bench_option_index or args.finish_setup_bench):
                    payload = {
                        "source": "clean-room native pregame",
                        "library": str(library_path),
                        "decks": {
                            "player": _deck_summary(args.deck, player_deck.cards),
                            "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
                        },
                        "native": {
                            "phase": "post_mulligan_draw_count_selected",
                            "setup": _setup_summary(setup, seed=args.seed, include_setup_details=True),
                            "active_selections": [
                                {
                                    "player_index": args.first_player,
                                    "option_index": args.setup_active_option_index,
                                    "hand_index": int(selected_option["index"]),
                                    "card_id": int(selected_option["cardId"]) if "cardId" in selected_option else None,
                                },
                                {
                                    "player_index": next_player,
                                    "option_index": args.next_setup_active_option_index,
                                    "hand_index": int(next_selected_option["index"]),
                                    "card_id": int(next_selected_option["cardId"])
                                    if "cardId" in next_selected_option
                                    else None,
                                },
                            ],
                            "draw_count_selection": draw_count_selections[-1],
                            "draw_count_selections": draw_count_selections,
                        },
                        "observation": observation,
                        "visualizer": {
                            "frame_count": len(setup_progress_frames),
                            "frames": setup_progress_frames,
                            "truncated": False,
                        },
                        "kaggle_submission_made": False,
                    }
                    print(json.dumps(payload, sort_keys=True))
                    return 0
            elif args.draw_count_choice:
                raise ValueError("no mulligan DrawCount prompt is pending")
            if args.setup_bench_option_index or args.finish_setup_bench:
                selected_bench_options = _setup_options(
                    setup,
                    core,
                    player_index=args.first_player,
                    option_indexes=args.setup_bench_option_index,
                    label="setup bench",
                )
                if selected_bench_options:
                    setup, selected_bench_selections = _apply_setup_bench_choices(
                        setup,
                        core,
                        player_index=args.first_player,
                        option_indexes=args.setup_bench_option_index,
                        selected_options=selected_bench_options,
                    )
                else:
                    setup = core.finish_setup_player(setup, player_index=args.first_player)
                    selected_bench_selections = []
                observation = setup.to_observation(player_index=next_player, native_core=core)
                next_bench_turn_action_count = len(setup_progress_frames) + 1
                observation["current"]["turnActionCount"] = next_bench_turn_action_count
                next_bench_frame = _visualizer_setup_active_frame(
                    setup,
                    core,
                    acting_player=next_player,
                    turn_action_count=next_bench_turn_action_count,
                )
                if args.next_setup_bench_option_index or args.finish_next_setup_bench:
                    next_selected_bench_options = _setup_options(
                        setup,
                        core,
                        player_index=next_player,
                        option_indexes=args.next_setup_bench_option_index,
                        label="next setup bench",
                    )
                    if next_selected_bench_options:
                        setup, next_selected_bench_selections = _apply_setup_bench_choices(
                            setup,
                            core,
                            player_index=next_player,
                            option_indexes=args.next_setup_bench_option_index,
                            selected_options=next_selected_bench_options,
                        )
                    else:
                        setup = core.finish_setup_player(setup, player_index=next_player)
                        next_selected_bench_selections = []
                    if args.begin_first_turn:
                        setup = core.begin_first_turn(setup)
                    acting_player = setup.current_player if args.begin_first_turn else next_player
                    observation = setup.to_observation(player_index=acting_player, native_core=core)
                    final_turn_action_count = next_bench_turn_action_count + 1
                    observation["current"]["turnActionCount"] = final_turn_action_count
                    final_frame = _visualizer_setup_active_frame(
                        setup,
                        core,
                        acting_player=acting_player,
                        turn_action_count=final_turn_action_count,
                    )
                    frames = setup_progress_frames + [next_bench_frame, final_frame]
                    payload = {
                        "source": "clean-room native pregame",
                        "library": str(library_path),
                        "decks": {
                            "player": _deck_summary(args.deck, player_deck.cards),
                            "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
                        },
                        "native": {
                            "phase": (
                                "post_setup_complete_first_turn_started"
                                if args.begin_first_turn
                                else "post_both_setup_players_finished"
                            ),
                            "setup": _setup_summary(setup, seed=args.seed, include_setup_details=True),
                            "active_selections": [
                                {
                                    "player_index": args.first_player,
                                    "option_index": args.setup_active_option_index,
                                    "hand_index": int(selected_option["index"]),
                                    "card_id": int(selected_option["cardId"])
                                    if "cardId" in selected_option
                                    else None,
                                },
                                {
                                    "player_index": next_player,
                                    "option_index": args.next_setup_active_option_index,
                                    "hand_index": int(next_selected_option["index"]),
                                    "card_id": int(next_selected_option["cardId"])
                                    if "cardId" in next_selected_option
                                    else None,
                                },
                            ],
                            "bench_selection": selected_bench_selections[0]
                            if selected_bench_selections
                            else None,
                            "bench_selections": selected_bench_selections + next_selected_bench_selections,
                        },
                        "observation": observation,
                        "visualizer": {
                            "frame_count": len(frames),
                            "frames": frames,
                            "truncated": False,
                        },
                        "kaggle_submission_made": False,
                    }
                    print(json.dumps(payload, sort_keys=True))
                    return 0
                frames = setup_progress_frames + [next_bench_frame]
                payload = {
                    "source": "clean-room native pregame",
                    "library": str(library_path),
                    "decks": {
                        "player": _deck_summary(args.deck, player_deck.cards),
                        "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
                    },
                    "native": {
                        "phase": "post_setup_bench_selected",
                        "setup": _setup_summary(setup, seed=args.seed, include_setup_details=True),
                        "active_selections": [
                            {
                                "player_index": args.first_player,
                                "option_index": args.setup_active_option_index,
                                "hand_index": int(selected_option["index"]),
                                "card_id": int(selected_option["cardId"]) if "cardId" in selected_option else None,
                            },
                            {
                                "player_index": next_player,
                                "option_index": args.next_setup_active_option_index,
                                "hand_index": int(next_selected_option["index"]),
                                "card_id": int(next_selected_option["cardId"])
                                if "cardId" in next_selected_option
                                else None,
                            },
                        ],
                        "bench_selection": selected_bench_selections[0]
                        if selected_bench_selections
                        else None,
                        "bench_selections": selected_bench_selections,
                    },
                    "observation": observation,
                    "visualizer": {
                        "frame_count": len(frames),
                        "frames": frames,
                        "truncated": False,
                    },
                    "kaggle_submission_made": False,
                }
                print(json.dumps(payload, sort_keys=True))
                return 0
            payload = {
                "source": "clean-room native pregame",
                "library": str(library_path),
                "decks": {
                    "player": _deck_summary(args.deck, player_deck.cards),
                    "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
                },
                "native": {
                    "phase": "post_both_setup_actives_selected",
                    "setup": _setup_summary(setup, seed=args.seed),
                    "active_selections": [
                        {
                            "player_index": args.first_player,
                            "option_index": args.setup_active_option_index,
                            "hand_index": int(selected_option["index"]),
                            "card_id": int(selected_option["cardId"]) if "cardId" in selected_option else None,
                        },
                        {
                            "player_index": next_player,
                            "option_index": args.next_setup_active_option_index,
                            "hand_index": int(next_selected_option["index"]),
                            "card_id": int(next_selected_option["cardId"]) if "cardId" in next_selected_option else None,
                        },
                    ],
                },
                "observation": observation,
                "visualizer": {
                    "frame_count": len(setup_progress_frames),
                    "frames": setup_progress_frames,
                    "truncated": False,
                },
                "kaggle_submission_made": False,
            }
            print(json.dumps(payload, sort_keys=True))
            return 0
        observation = setup.to_observation(player_index=next_player, native_core=core)
        observation["current"]["turnActionCount"] = 3
        payload = {
            "source": "clean-room native pregame",
            "library": str(library_path),
            "decks": {
                "player": _deck_summary(args.deck, player_deck.cards),
                "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
            },
            "native": {
                "phase": "post_setup_active_selected",
                "setup": _setup_summary(setup, seed=args.seed),
                "active_selection": {
                    "player_index": args.first_player,
                    "option_index": args.setup_active_option_index,
                    "hand_index": int(selected_option["index"]),
                    "card_id": int(selected_option["cardId"]) if "cardId" in selected_option else None,
                },
            },
            "observation": observation,
            "visualizer": {
                "frame_count": 3,
                "frames": [
                    _pregame_visualizer_frame(pregame),
                    post_isfirst_frame,
                    next_player_frame,
                ],
                "truncated": False,
            },
            "kaggle_submission_made": False,
        }
        print(json.dumps(payload, sort_keys=True))
        return 0

    payload = {
        "source": "clean-room native pregame",
        "library": str(library_path),
        "decks": {
            "player": _deck_summary(args.deck, player_deck.cards),
            "opponent": _deck_summary(opponent_deck, opponent_loaded_deck.cards),
        },
        "native": {
            "phase": "post_isfirst_opening_hand",
            "setup": _setup_summary(setup, seed=args.seed),
        },
        "observation": observation,
        "visualizer": {
            "frame_count": 2,
            "frames": [
                _pregame_visualizer_frame(pregame),
                post_isfirst_frame,
            ],
            "truncated": False,
        },
        "kaggle_submission_made": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
