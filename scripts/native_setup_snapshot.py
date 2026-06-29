from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg.native_core import NativeCore, build_native_core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a native setup snapshot for the web simulator bridge.")
    parser.add_argument("--deck", type=Path, default=Path("deck.csv"))
    parser.add_argument("--opponent-deck", type=Path, default=None)
    parser.add_argument("--player-index", type=int, choices=(0, 1), default=0)
    parser.add_argument("--view-player-index", type=int, choices=(0, 1), default=None)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--active-hand-index", type=int, default=None)
    parser.add_argument("--bench-hand-index", type=int, action="append", default=[])
    parser.add_argument("--finish-setup", action="store_true")
    parser.add_argument("--player0-active-hand-index", type=int, default=None)
    parser.add_argument("--player1-active-hand-index", type=int, default=None)
    parser.add_argument("--player0-bench-hand-index", type=int, action="append", default=[])
    parser.add_argument("--player1-bench-hand-index", type=int, action="append", default=[])
    parser.add_argument("--finish-player0-setup", action="store_true")
    parser.add_argument("--finish-player1-setup", action="store_true")
    parser.add_argument("--draw-count-choice", type=int, action="append", default=[])
    parser.add_argument("--auto-finish-remaining-setup", action="store_true")
    parser.add_argument("--begin-first-turn", action="store_true")
    parser.add_argument("--end-turn-count", type=int, default=0)
    parser.add_argument("--main-action", action="append", default=[])
    parser.add_argument("--build-dir", type=Path, default=Path("artifacts/native_api"))
    args = parser.parse_args(argv)

    library_path = build_native_core(build_dir=args.build_dir)
    core = NativeCore(library_path)
    opponent_deck = args.opponent_deck or args.deck
    setup = core.start_battle_setup(args.deck, opponent_deck, seed=args.seed)
    setup = _apply_setup_active_choice(
        core,
        setup,
        player_index=args.player_index,
        active_hand_index=args.active_hand_index,
    )
    setup = _apply_setup_active_choice(
        core,
        setup,
        player_index=0,
        active_hand_index=args.player0_active_hand_index,
    )
    setup = _apply_setup_active_choice(
        core,
        setup,
        player_index=1,
        active_hand_index=args.player1_active_hand_index,
    )
    setup = _apply_draw_count_choices(core, setup, args.draw_count_choice)
    setup = _apply_setup_bench_and_finish_choices(
        core,
        setup,
        player_index=args.player_index,
        bench_hand_indexes=args.bench_hand_index,
        finish_setup=args.finish_setup,
    )
    setup = _apply_setup_bench_and_finish_choices(
        core,
        setup,
        player_index=0,
        bench_hand_indexes=args.player0_bench_hand_index,
        finish_setup=args.finish_player0_setup,
    )
    setup = _apply_setup_bench_and_finish_choices(
        core,
        setup,
        player_index=1,
        bench_hand_indexes=args.player1_bench_hand_index,
        finish_setup=args.finish_player1_setup,
    )
    if args.auto_finish_remaining_setup:
        setup = _auto_finish_remaining_setup(core, setup)
    if args.begin_first_turn:
        setup = core.begin_first_turn(setup)
    for _ in range(args.end_turn_count):
        setup = core.end_turn(setup)
    for main_action in args.main_action:
        setup = _apply_main_action(core, setup, main_action)
    payload = {
        "library": str(library_path),
            "setup": {
                "seed": args.seed,
                "turn": setup.turn,
                "first_player": setup.first_player,
                "current_player": setup.current_player,
                "mulligans": list(setup.setup_mulligans),
                "mulligan_draw_choices": list(setup.setup_mulligan_draw_choices),
                "pending_promotion_player": setup.pending_promotion_player,
            "pending_promotion_next_player": setup.pending_promotion_next_player,
            "pending_boss_orders_player": setup.pending_boss_orders_player,
            "pending_heave_ho_player": setup.pending_heave_ho_player,
            "pending_fighting_gong_player": setup.pending_fighting_gong_player,
            "pending_poke_pad_player": setup.pending_poke_pad_player,
            "pending_switch_player": setup.pending_switch_player,
            "pending_retreat_player": setup.pending_retreat_player,
            "pending_retreat_remaining": setup.pending_retreat_remaining,
            "pending_aura_jab_player": setup.pending_aura_jab_player,
            "pending_aura_jab_remaining": setup.pending_aura_jab_remaining,
            "supporter_played": setup.supporter_played,
            "retreated": setup.retreated,
            "lunar_cycle_used": setup.lunar_cycle_used,
            "fighting_attack_bonus": setup.fighting_attack_bonus,
            "stadium_played": setup.stadium_played,
            "stadium_card_id": setup.stadium_card_id,
            "stadium_player_index": setup.stadium_player_index,
            "complete": core.is_setup_complete(setup),
            "players": [
                {
                    "deck_count": player.deck_count,
                    "hand_count": player.hand_count,
                    "prize_count": player.prize_count,
                    "active_card_id": player.active_card_id,
                    "bench_count": len(player.bench_card_ids),
                    "setup_complete": player.setup_complete,
                }
                for player in setup.players
            ],
        },
        "observation": setup.to_observation(player_index=args.player_index, native_core=core),
        "kaggle_submission_made": False,
    }
    if args.view_player_index is not None:
        payload["viewer_observation"] = setup.to_observation(
            player_index=args.player_index,
            view_player_index=args.view_player_index,
            suppress_options_when_waiting=True,
            native_core=core,
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


def _apply_main_action(core: NativeCore, setup, action: str):
    parts = action.split(":")
    if parts[0] == "end" and len(parts) == 1:
        return core.end_turn(setup)
    if parts[0] == "play" and len(parts) == 2:
        return core.play_basic_to_bench(setup, hand_index=int(parts[1]))
    if parts[0] == "dusk" and len(parts) == 2:
        return core.play_dusk_ball(setup, hand_index=int(parts[1]))
    if parts[0] == "duskpick" and len(parts) == 2:
        return core.resolve_dusk_ball(setup, deck_index=int(parts[1]), reveal=True)
    if parts[0] == "duskskip" and len(parts) == 1:
        return core.resolve_dusk_ball(setup, reveal=False)
    if parts[0] == "gong" and len(parts) == 2:
        return core.play_fighting_gong(setup, hand_index=int(parts[1]))
    if parts[0] == "powerpro" and len(parts) == 2:
        return core.play_premium_power_pro(setup, hand_index=int(parts[1]))
    if parts[0] == "lunar" and len(parts) == 2:
        return core.use_lunar_cycle(setup, hand_index=int(parts[1]))
    if parts[0] == "stadium" and len(parts) == 2:
        return core.play_gravity_mountain(setup, hand_index=int(parts[1]))
    if parts[0] == "gongpick" and len(parts) == 2:
        return core.resolve_fighting_gong(setup, deck_index=int(parts[1]), reveal=True)
    if parts[0] == "gongskip" and len(parts) == 1:
        return core.resolve_fighting_gong(setup, reveal=False)
    if parts[0] == "pokepad" and len(parts) == 2:
        return core.play_poke_pad(setup, hand_index=int(parts[1]))
    if parts[0] == "pokepadpick" and len(parts) == 2:
        return core.resolve_poke_pad(setup, deck_index=int(parts[1]), reveal=True)
    if parts[0] == "pokepadskip" and len(parts) == 1:
        return core.resolve_poke_pad(setup, reveal=False)
    if parts[0] == "switch" and len(parts) == 2:
        return core.play_switch(setup, hand_index=int(parts[1]))
    if parts[0] == "switchtarget" and len(parts) == 2:
        return core.resolve_switch(setup, bench_index=int(parts[1]))
    if parts[0] == "retreat" and len(parts) == 1:
        return core.start_retreat(setup)
    if parts[0] == "retreatdiscard" and len(parts) == 2:
        return core.resolve_retreat_discard(setup, energy_index=int(parts[1]))
    if parts[0] == "retreattarget" and len(parts) == 2:
        return core.resolve_retreat_promote(setup, bench_index=int(parts[1]))
    if parts[0] == "lillie" and len(parts) == 2:
        return core.play_lillies_determination(setup, hand_index=int(parts[1]))
    if parts[0] == "carmine" and len(parts) == 2:
        return core.play_carmine(setup, hand_index=int(parts[1]))
    if parts[0] == "boss" and len(parts) == 2:
        return core.play_boss_orders(setup, hand_index=int(parts[1]))
    if parts[0] == "bosstarget" and len(parts) == 2:
        return core.resolve_boss_orders(setup, bench_index=int(parts[1]))
    if parts[0] == "heavehotarget" and len(parts) == 2:
        return core.resolve_heave_ho_catcher(setup, bench_index=int(parts[1]))
    if parts[0] == "heavehoskip" and len(parts) == 1:
        return core.skip_heave_ho_catcher(setup)
    if parts[0] == "evolve" and len(parts) == 4:
        return core.evolve_from_hand(
            setup,
            hand_index=int(parts[1]),
            in_play_area=int(parts[2]),
            in_play_index=int(parts[3]),
        )
    if parts[0] == "attach" and len(parts) == 4:
        return core.attach_energy(
            setup,
            hand_index=int(parts[1]),
            in_play_area=int(parts[2]),
            in_play_index=int(parts[3]),
        )
    if parts[0] == "hero" and len(parts) == 4:
        return core.attach_heros_cape(
            setup,
            hand_index=int(parts[1]),
            in_play_area=int(parts[2]),
            in_play_index=int(parts[3]),
        )
    if parts[0] == "attack" and len(parts) == 2:
        return core.use_attack(setup, attack_id=int(parts[1]))
    if parts[0] == "aurajab" and len(parts) == 3:
        return core.resolve_aura_jab_attach(
            setup,
            discard_index=int(parts[1]),
            bench_index=int(parts[2]),
        )
    if parts[0] == "aurajabskip" and len(parts) == 1:
        return core.skip_aura_jab(setup)
    if parts[0] == "promote" and len(parts) == 2:
        if setup.pending_promotion_player is None:
            raise ValueError("cannot promote without a pending Active promotion")
        return core.promote_bench_to_active(
            setup,
            player_index=setup.pending_promotion_player,
            bench_index=int(parts[1]),
        )
    if parts[0] == "promote" and len(parts) == 3:
        return core.promote_bench_to_active(
            setup,
            player_index=int(parts[1]),
            bench_index=int(parts[2]),
        )
    raise ValueError(f"unsupported main action: {action}")


def _apply_setup_active_choice(
    core: NativeCore,
    setup,
    *,
    player_index: int,
    active_hand_index: int | None,
):
    if active_hand_index is not None:
        setup = core.select_setup_active(
            setup,
            player_index=player_index,
            hand_index=active_hand_index,
        )
    return setup


def _apply_draw_count_choices(core: NativeCore, setup, choices: list[int]):
    for choice in choices:
        setup = core.apply_pregame_draw_count(setup, count=choice)
    return setup


def _apply_setup_bench_and_finish_choices(
    core: NativeCore,
    setup,
    *,
    player_index: int,
    bench_hand_indexes: list[int],
    finish_setup: bool,
):
    for bench_hand_index in bench_hand_indexes:
        setup = core.select_setup_bench(
            setup,
            player_index=player_index,
            hand_index=bench_hand_index,
        )
    if finish_setup:
        setup = core.finish_setup_player(setup, player_index=player_index)
    return setup


def _auto_finish_remaining_setup(core: NativeCore, setup):
    for player_index, player in enumerate(setup.players):
        if player.setup_complete:
            continue
        if player.active_card_id is None:
            active_hand_index = _first_basic_hand_index(core, player.hand_card_ids)
            setup = core.select_setup_active(
                setup,
                player_index=player_index,
                hand_index=active_hand_index,
            )
        setup = core.finish_setup_player(setup, player_index=player_index)
    return setup


def _first_basic_hand_index(core: NativeCore, hand_card_ids: tuple[int, ...]) -> int:
    for index, card_id in enumerate(hand_card_ids):
        if core.is_basic_pokemon_card(card_id):
            return index
    raise ValueError("no Basic Pokemon is available to finish setup")


if __name__ == "__main__":
    raise SystemExit(main())
