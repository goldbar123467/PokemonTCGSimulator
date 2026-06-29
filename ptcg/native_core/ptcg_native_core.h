#ifndef PTCG_NATIVE_CORE_H
#define PTCG_NATIVE_CORE_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
#if defined(PTCG_NATIVE_BUILD)
#define PTCG_API __declspec(dllexport)
#else
#define PTCG_API __declspec(dllimport)
#endif
#else
#define PTCG_API __attribute__((visibility("default")))
#endif

#define PTCG_DECK_SIZE 60
#define PTCG_SETUP_HAND_SIZE 7
#define PTCG_HAND_SIZE 60
#define PTCG_DISCARD_SIZE 120
#define PTCG_PRIZE_SIZE 6
#define PTCG_BENCH_SIZE 5
#define PTCG_ATTACHED_SIZE 60
#define PTCG_PRE_EVOLUTION_SIZE 3
#define PTCG_CARD_ATTACK_SIZE 2
#define PTCG_ATTACK_COST_SIZE 5
#define PTCG_AREA_DECK 1
#define PTCG_AREA_HAND 2
#define PTCG_AREA_DISCARD 3
#define PTCG_AREA_ACTIVE 4
#define PTCG_AREA_BENCH 5
#define PTCG_ENERGY_COLORLESS 0
#define PTCG_ENERGY_FIGHTING 6
#define PTCG_ENERGY_RAINBOW 10
#define PTCG_NO_ENERGY_TYPE -1
#define PTCG_RESISTANCE_DAMAGE_REDUCTION 30
#define PTCG_CARD_DUSK_BALL 1102
#define PTCG_CARD_SWITCH 1123
#define PTCG_CARD_PREMIUM_POWER_PRO 1141
#define PTCG_CARD_FIGHTING_GONG 1142
#define PTCG_CARD_POKE_PAD 1152
#define PTCG_CARD_HEROS_CAPE 1159
#define PTCG_CARD_BOSS_ORDERS 1182
#define PTCG_CARD_CARMINE 1192
#define PTCG_CARD_LILLIES_DETERMINATION 1227
#define PTCG_CARD_GRAVITY_MOUNTAIN 1252
#define PTCG_CARD_HARIYAMA 674
#define PTCG_CARD_LUNATONE 675
#define PTCG_CARD_SOLROCK 676
#define PTCG_ATTACK_WILD_PRESS 978
#define PTCG_ATTACK_COSMIC_BEAM 980
#define PTCG_ATTACK_ACCELERATING_STAB 981
#define PTCG_ATTACK_AURA_JAB 982
#define PTCG_ATTACK_MEGA_BRAVE 983

typedef struct PtcgDeck {
    int card_count;
    int cards[PTCG_DECK_SIZE];
} PtcgDeck;

typedef struct PtcgDeckNamedCount {
    int card_id;
    int count;
    char name[96];
} PtcgDeckNamedCount;

typedef struct PtcgBattlePlayer {
    int deck_count;
    int deck[PTCG_DECK_SIZE];
    int hand_count;
    int hand[PTCG_HAND_SIZE];
    int discard_count;
    int discard[PTCG_DISCARD_SIZE];
    int prize_count;
    int prize[PTCG_PRIZE_SIZE];
    int active_card_id;
    int active_damage;
    int active_entered_turn;
    int active_evolved_turn;
    int active_pre_evolution_count;
    int active_pre_evolution[PTCG_PRE_EVOLUTION_SIZE];
    int active_energy_count;
    int active_energy[PTCG_ATTACHED_SIZE];
    int active_tool_card_id;
    int active_disabled_attack_id;
    int active_disabled_attack_turn;
    int bench_count;
    int bench[PTCG_BENCH_SIZE];
    int bench_damage[PTCG_BENCH_SIZE];
    int bench_entered_turn[PTCG_BENCH_SIZE];
    int bench_evolved_turn[PTCG_BENCH_SIZE];
    int bench_pre_evolution_count[PTCG_BENCH_SIZE];
    int bench_pre_evolution[PTCG_BENCH_SIZE][PTCG_PRE_EVOLUTION_SIZE];
    int bench_energy_count[PTCG_BENCH_SIZE];
    int bench_energy[PTCG_BENCH_SIZE][PTCG_ATTACHED_SIZE];
    int bench_tool[PTCG_BENCH_SIZE];
} PtcgBattlePlayer;

typedef struct PtcgBattleSetup {
    int turn;
    int first_player;
    int current_player;
    int setup_complete[2];
    int setup_mulligans[2];
    int setup_mulligan_draw_choices[2];
    int energy_attached;
    int retreated;
    int supporter_played;
    int lunar_cycle_used;
    int stadium_played;
    int stadium_card_id;
    int stadium_player_index;
    int fighting_attack_bonus;
    int result;
    int pending_promotion_player;
    int pending_promotion_next_player;
    int pending_dusk_ball_player;
    int pending_dusk_ball_start;
    int pending_dusk_ball_count;
    int pending_boss_orders_player;
    int pending_heave_ho_player;
    int pending_fighting_gong_player;
    int pending_poke_pad_player;
    int pending_switch_player;
    int pending_retreat_player;
    int pending_retreat_remaining;
    int pending_aura_jab_player;
    int pending_aura_jab_remaining;
    PtcgBattlePlayer players[2];
} PtcgBattleSetup;

typedef struct PtcgCardMetadata {
    int card_id;
    int card_type;
    int hp;
    int basic;
    int stage1;
    int stage2;
    int energy_type;
    int retreat_cost;
    int weakness_type;
    int resistance_type;
    int ex;
    int mega_ex;
    char evolves_from[96];
    int attack_count;
    int attacks[PTCG_CARD_ATTACK_SIZE];
    char name[96];
} PtcgCardMetadata;

typedef struct PtcgAttackMetadata {
    int attack_id;
    int damage;
    int energy_count;
    int energies[PTCG_ATTACK_COST_SIZE];
    char name[96];
} PtcgAttackMetadata;

PTCG_API const char *ptcg_native_version(void);
PTCG_API int ptcg_get_card_metadata(int card_id, PtcgCardMetadata *out_metadata);
PTCG_API int ptcg_get_attack_metadata(int attack_id, PtcgAttackMetadata *out_metadata);
PTCG_API int ptcg_is_basic_pokemon_card(int card_id);
PTCG_API int ptcg_is_energy_card(int card_id);
PTCG_API int ptcg_can_use_attack(
    int card_id,
    int attack_id,
    const int *energy_card_ids,
    int energy_count
);
PTCG_API int ptcg_load_deck_csv(const char *path, PtcgDeck *out_deck, char *message, int message_len);
PTCG_API int ptcg_deck_count_card(const PtcgDeck *deck, int card_id);
PTCG_API int ptcg_deck_unique_count(const PtcgDeck *deck);
PTCG_API int ptcg_deck_basic_pokemon_count(const PtcgDeck *deck);
PTCG_API int ptcg_deck_energy_count(const PtcgDeck *deck);
PTCG_API int ptcg_deck_named_counts(
    const PtcgDeck *deck,
    PtcgDeckNamedCount *out_counts,
    int max_counts
);
PTCG_API int ptcg_start_battle_pregame_from_csv(
    const char *deck_path,
    const char *opponent_deck_path,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_select_pregame_first_player(
    const PtcgBattleSetup *pregame,
    int first_player,
    unsigned int seed,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_start_battle_setup_from_csv(
    const char *deck_path,
    const char *opponent_deck_path,
    unsigned int seed,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_select_setup_active(
    const PtcgBattleSetup *setup,
    int player_index,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_deal_setup_prizes(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_select_setup_bench(
    const PtcgBattleSetup *setup,
    int player_index,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_finish_setup_player(
    const PtcgBattleSetup *setup,
    int player_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_is_setup_complete(const PtcgBattleSetup *setup);
PTCG_API int ptcg_begin_first_turn(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_end_turn(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_basic_to_bench(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_evolve_from_hand(
    const PtcgBattleSetup *setup,
    int hand_index,
    int in_play_area,
    int in_play_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_attach_energy(
    const PtcgBattleSetup *setup,
    int hand_index,
    int in_play_area,
    int in_play_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_attach_heros_cape(
    const PtcgBattleSetup *setup,
    int hand_index,
    int in_play_area,
    int in_play_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_dusk_ball(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_dusk_ball(
    const PtcgBattleSetup *setup,
    int deck_index,
    int reveal,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_fighting_gong(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_premium_power_pro(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_use_lunar_cycle(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_fighting_gong(
    const PtcgBattleSetup *setup,
    int deck_index,
    int reveal,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_poke_pad(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_poke_pad(
    const PtcgBattleSetup *setup,
    int deck_index,
    int reveal,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_lillies_determination(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_carmine(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_switch(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_switch(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_start_retreat(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_retreat_discard(
    const PtcgBattleSetup *setup,
    int energy_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_retreat_promote(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_boss_orders(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_boss_orders(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_heave_ho_catcher(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_skip_heave_ho_catcher(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_play_gravity_mountain(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_promote_bench_to_active(
    const PtcgBattleSetup *setup,
    int player_index,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_resolve_aura_jab_attach(
    const PtcgBattleSetup *setup,
    int discard_index,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_skip_aura_jab(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);
PTCG_API int ptcg_use_attack(
    const PtcgBattleSetup *setup,
    int attack_id,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
);

#ifdef __cplusplus
}
#endif

#endif
