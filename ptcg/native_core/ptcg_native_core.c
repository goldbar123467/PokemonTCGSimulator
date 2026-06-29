#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PTCG_NATIVE_BUILD 1
#include "ptcg_native_core.h"
#include "ptcg_card_catalog.generated.h"

static void set_message(char *message, int message_len, const char *text) {
    if (message == NULL || message_len <= 0) {
        return;
    }
    snprintf(message, (size_t)message_len, "%s", text);
}

static void set_count_message(char *message, int message_len, int count) {
    if (message == NULL || message_len <= 0) {
        return;
    }
    snprintf(
        message,
        (size_t)message_len,
        "expected 60 cards in deck.csv, found %d",
        count
    );
}

static char *trim_left(char *text) {
    while (*text != '\0' && isspace((unsigned char)*text)) {
        text += 1;
    }
    return text;
}

static void trim_right(char *text) {
    size_t len = strlen(text);
    while (len > 0 && isspace((unsigned char)text[len - 1])) {
        text[len - 1] = '\0';
        len -= 1;
    }
}

PTCG_API const char *ptcg_native_version(void) {
    return "ptcg-native-core/0.1.0";
}

static const PtcgCardCatalogEntry *find_card_entry(int card_id) {
    int left = 0;
    int right = PTCG_CARD_CATALOG_COUNT - 1;
    while (left <= right) {
        int middle = left + (right - left) / 2;
        int current = PTCG_CARD_CATALOG[middle].card_id;
        if (current == card_id) {
            return &PTCG_CARD_CATALOG[middle];
        }
        if (current < card_id) {
            left = middle + 1;
        } else {
            right = middle - 1;
        }
    }
    return NULL;
}

static const PtcgAttackCatalogEntry *find_attack_entry(int attack_id) {
    int left = 0;
    int right = PTCG_ATTACK_CATALOG_COUNT - 1;
    while (left <= right) {
        int middle = left + (right - left) / 2;
        int current = PTCG_ATTACK_CATALOG[middle].attack_id;
        if (current == attack_id) {
            return &PTCG_ATTACK_CATALOG[middle];
        }
        if (current < attack_id) {
            left = middle + 1;
        } else {
            right = middle - 1;
        }
    }
    return NULL;
}

PTCG_API int ptcg_get_card_metadata(int card_id, PtcgCardMetadata *out_metadata) {
    const PtcgCardCatalogEntry *entry = find_card_entry(card_id);
    int index = 0;
    if (out_metadata == NULL) {
        return 2;
    }
    memset(out_metadata, 0, sizeof(PtcgCardMetadata));
    if (entry == NULL) {
        return 1;
    }
    out_metadata->card_id = entry->card_id;
    out_metadata->card_type = entry->card_type;
    out_metadata->hp = entry->hp;
    out_metadata->basic = entry->basic;
    out_metadata->stage1 = entry->stage1;
    out_metadata->stage2 = entry->stage2;
    out_metadata->energy_type = entry->energy_type;
    out_metadata->retreat_cost = entry->retreat_cost;
    out_metadata->weakness_type = entry->weakness_type;
    out_metadata->resistance_type = entry->resistance_type;
    out_metadata->ex = entry->ex;
    out_metadata->mega_ex = entry->mega_ex;
    if (entry->evolves_from != NULL) {
        snprintf(out_metadata->evolves_from, sizeof(out_metadata->evolves_from), "%s", entry->evolves_from);
    }
    out_metadata->attack_count = entry->attack_count;
    for (index = 0; index < PTCG_CARD_ATTACK_SIZE; index += 1) {
        out_metadata->attacks[index] = entry->attacks[index];
    }
    snprintf(out_metadata->name, sizeof(out_metadata->name), "%s", entry->name);
    return 0;
}

PTCG_API int ptcg_get_attack_metadata(int attack_id, PtcgAttackMetadata *out_metadata) {
    const PtcgAttackCatalogEntry *entry = find_attack_entry(attack_id);
    int index = 0;
    if (out_metadata == NULL) {
        return 2;
    }
    memset(out_metadata, 0, sizeof(PtcgAttackMetadata));
    if (entry == NULL) {
        return 1;
    }
    out_metadata->attack_id = entry->attack_id;
    out_metadata->damage = entry->damage;
    out_metadata->energy_count = entry->energy_count;
    for (index = 0; index < PTCG_ATTACK_COST_SIZE; index += 1) {
        out_metadata->energies[index] = entry->energies[index];
    }
    snprintf(out_metadata->name, sizeof(out_metadata->name), "%s", entry->name);
    return 0;
}

PTCG_API int ptcg_is_basic_pokemon_card(int card_id) {
    const PtcgCardCatalogEntry *entry = find_card_entry(card_id);
    if (entry == NULL) {
        return 0;
    }
    return entry->card_type == 0 && entry->basic != 0;
}

PTCG_API int ptcg_is_energy_card(int card_id) {
    const PtcgCardCatalogEntry *entry = find_card_entry(card_id);
    if (entry == NULL) {
        return 0;
    }
    return entry->card_type == 5 || entry->card_type == 6;
}

static int card_has_attack(const PtcgCardCatalogEntry *card, int attack_id) {
    int index = 0;
    if (card == NULL) {
        return 0;
    }
    for (index = 0; index < card->attack_count && index < PTCG_CARD_ATTACK_SIZE; index += 1) {
        if (card->attacks[index] == attack_id) {
            return 1;
        }
    }
    return 0;
}

static int attack_locks_next_turn(int attack_id) {
    return attack_id == PTCG_ATTACK_ACCELERATING_STAB || attack_id == PTCG_ATTACK_MEGA_BRAVE;
}

static int active_attack_is_disabled(const PtcgBattlePlayer *player, int attack_id, int turn) {
    return (
        player != NULL
        && player->active_disabled_attack_id == attack_id
        && player->active_disabled_attack_turn == turn
    );
}

static void clear_active_attack_lock(PtcgBattlePlayer *player) {
    if (player == NULL) {
        return;
    }
    player->active_disabled_attack_id = 0;
    player->active_disabled_attack_turn = 0;
}

static void set_disabled_attack_message(
    char *message,
    int message_len,
    const PtcgAttackCatalogEntry *attack
) {
    if (message == NULL || message_len <= 0) {
        return;
    }
    snprintf(
        message,
        (size_t)message_len,
        "%s cannot be used during this Pokemon's next turn",
        attack == NULL ? "That attack" : attack->name
    );
}

static int is_first_players_first_turn(const PtcgBattleSetup *setup) {
    return (
        setup != NULL
        && setup->turn == 1
        && setup->current_player == setup->first_player
    );
}

static int player_has_benched_card(const PtcgBattlePlayer *player, int card_id) {
    int index = 0;
    if (player == NULL) {
        return 0;
    }
    for (index = 0; index < player->bench_count; index += 1) {
        if (player->bench[index] == card_id) {
            return 1;
        }
    }
    return 0;
}

static int player_has_card_in_play(const PtcgBattlePlayer *player, int card_id) {
    if (player == NULL) {
        return 0;
    }
    if (player->active_card_id == card_id) {
        return 1;
    }
    return player_has_benched_card(player, card_id);
}

static int attack_ignores_weakness_resistance(int attack_id) {
    return attack_id == PTCG_ATTACK_COSMIC_BEAM;
}

static int apply_weakness_resistance(
    int damage,
    const PtcgCardCatalogEntry *attacking_card,
    const PtcgCardCatalogEntry *defending_card,
    int attack_id
) {
    if (
        damage <= 0
        || attacking_card == NULL
        || defending_card == NULL
        || attack_ignores_weakness_resistance(attack_id)
    ) {
        return damage;
    }
    if (
        defending_card->weakness_type != PTCG_NO_ENERGY_TYPE
        && defending_card->weakness_type == attacking_card->energy_type
    ) {
        damage *= 2;
    }
    if (
        defending_card->resistance_type != PTCG_NO_ENERGY_TYPE
        && defending_card->resistance_type == attacking_card->energy_type
    ) {
        damage -= PTCG_RESISTANCE_DAMAGE_REDUCTION;
        if (damage < 0) {
            damage = 0;
        }
    }
    return damage;
}

static int calculate_attack_damage(
    const PtcgBattleSetup *setup,
    const PtcgBattlePlayer *attacker,
    const PtcgCardCatalogEntry *attacking_card,
    const PtcgCardCatalogEntry *defending_card,
    const PtcgAttackCatalogEntry *attack,
    int attack_id
) {
    int damage = attack == NULL ? 0 : attack->damage;
    if (attack_id == PTCG_ATTACK_COSMIC_BEAM && !player_has_benched_card(attacker, PTCG_CARD_LUNATONE)) {
        return 0;
    }
    if (
        damage > 0
        && attacking_card != NULL
        && attacking_card->energy_type == PTCG_ENERGY_FIGHTING
        && setup != NULL
        && setup->fighting_attack_bonus > 0
    ) {
        damage += setup->fighting_attack_bonus;
    }
    return apply_weakness_resistance(damage, attacking_card, defending_card, attack_id);
}

static int attack_self_damage(int attack_id) {
    if (attack_id == PTCG_ATTACK_WILD_PRESS) {
        return 70;
    }
    return 0;
}

static int tool_hp_bonus(int tool_card_id) {
    if (tool_card_id == PTCG_CARD_HEROS_CAPE) {
        return 100;
    }
    return 0;
}

static int stadium_hp_modifier(const PtcgCardCatalogEntry *card, int stadium_card_id) {
    if (card != NULL && stadium_card_id == PTCG_CARD_GRAVITY_MOUNTAIN && card->stage2 != 0) {
        return -30;
    }
    return 0;
}

static int effective_hp_for_card(const PtcgCardCatalogEntry *card, int tool_card_id, int stadium_card_id) {
    int hp = 0;
    if (card == NULL || card->hp <= 0) {
        return 0;
    }
    hp = card->hp + tool_hp_bonus(tool_card_id) + stadium_hp_modifier(card, stadium_card_id);
    return hp > 0 ? hp : 0;
}

static int can_pay_attack_cost(
    const PtcgAttackCatalogEntry *attack,
    const int *energy_card_ids,
    int energy_count
) {
    int used[PTCG_ATTACHED_SIZE];
    int cost_index = 0;
    int attached_index = 0;

    if (attack == NULL || energy_count < 0 || energy_count > PTCG_ATTACHED_SIZE) {
        return 0;
    }
    memset(used, 0, sizeof(used));

    for (cost_index = 0; cost_index < attack->energy_count && cost_index < PTCG_ATTACK_COST_SIZE; cost_index += 1) {
        int required_type = attack->energies[cost_index];
        if (required_type == PTCG_ENERGY_COLORLESS) {
            continue;
        }
        for (attached_index = 0; attached_index < energy_count; attached_index += 1) {
            const PtcgCardCatalogEntry *energy = NULL;
            if (used[attached_index] != 0) {
                continue;
            }
            energy = find_card_entry(energy_card_ids[attached_index]);
            if (energy == NULL || !ptcg_is_energy_card(energy->card_id)) {
                continue;
            }
            if (energy->energy_type == required_type || energy->energy_type == PTCG_ENERGY_RAINBOW) {
                used[attached_index] = 1;
                break;
            }
        }
        if (attached_index >= energy_count) {
            return 0;
        }
    }

    for (cost_index = 0; cost_index < attack->energy_count && cost_index < PTCG_ATTACK_COST_SIZE; cost_index += 1) {
        int required_type = attack->energies[cost_index];
        if (required_type != PTCG_ENERGY_COLORLESS) {
            continue;
        }
        for (attached_index = 0; attached_index < energy_count; attached_index += 1) {
            const PtcgCardCatalogEntry *energy = NULL;
            if (used[attached_index] != 0) {
                continue;
            }
            energy = find_card_entry(energy_card_ids[attached_index]);
            if (energy == NULL || !ptcg_is_energy_card(energy->card_id)) {
                continue;
            }
            used[attached_index] = 1;
            break;
        }
        if (attached_index >= energy_count) {
            return 0;
        }
    }

    return attack->energy_count <= PTCG_ATTACK_COST_SIZE;
}

PTCG_API int ptcg_can_use_attack(
    int card_id,
    int attack_id,
    const int *energy_card_ids,
    int energy_count
) {
    const PtcgCardCatalogEntry *card = find_card_entry(card_id);
    const PtcgAttackCatalogEntry *attack = find_attack_entry(attack_id);
    if (card == NULL || attack == NULL || energy_card_ids == NULL) {
        return 0;
    }
    if (!card_has_attack(card, attack_id)) {
        return 0;
    }
    return can_pay_attack_cost(attack, energy_card_ids, energy_count);
}

PTCG_API int ptcg_load_deck_csv(const char *path, PtcgDeck *out_deck, char *message, int message_len) {
    char line[256];
    int count = 0;
    FILE *file = NULL;

    if (out_deck == NULL) {
        set_message(message, message_len, "out_deck pointer is null");
        return 5;
    }
    memset(out_deck, 0, sizeof(PtcgDeck));

    if (path == NULL || path[0] == '\0') {
        set_message(message, message_len, "deck path is empty");
        return 1;
    }

    file = fopen(path, "rb");
    if (file == NULL) {
        set_message(message, message_len, "could not open deck.csv");
        return 1;
    }

    while (fgets(line, sizeof(line), file) != NULL) {
        char *start = trim_left(line);
        char *end = NULL;
        long parsed = 0;

        trim_right(start);
        if (start[0] == '\0') {
            continue;
        }

        if (count >= PTCG_DECK_SIZE) {
            fclose(file);
            set_count_message(message, message_len, count + 1);
            return 2;
        }

        errno = 0;
        parsed = strtol(start, &end, 10);
        if (errno != 0 || end == start || *end != '\0' || parsed > INT_MAX || parsed <= 0) {
            fclose(file);
            set_message(message, message_len, "invalid integer card id in deck.csv");
            return 3;
        }

        out_deck->cards[count] = (int)parsed;
        count += 1;
    }

    if (ferror(file)) {
        fclose(file);
        set_message(message, message_len, "failed while reading deck.csv");
        return 4;
    }
    fclose(file);

    if (count != PTCG_DECK_SIZE) {
        set_count_message(message, message_len, count);
        return 2;
    }

    out_deck->card_count = count;
    set_message(message, message_len, "ok");
    return 0;
}

static int valid_deck_count(const PtcgDeck *deck) {
    if (deck == NULL || deck->card_count < 0 || deck->card_count > PTCG_DECK_SIZE) {
        return 0;
    }
    return deck->card_count;
}

PTCG_API int ptcg_deck_count_card(const PtcgDeck *deck, int card_id) {
    int count = 0;
    int index = 0;
    int deck_count = valid_deck_count(deck);
    for (index = 0; index < deck_count; index += 1) {
        if (deck->cards[index] == card_id) {
            count += 1;
        }
    }
    return count;
}

static int card_seen_before(const PtcgDeck *deck, int index) {
    int previous = 0;
    if (deck == NULL || index < 0 || index >= deck->card_count) {
        return 0;
    }
    for (previous = 0; previous < index; previous += 1) {
        if (deck->cards[previous] == deck->cards[index]) {
            return 1;
        }
    }
    return 0;
}

PTCG_API int ptcg_deck_unique_count(const PtcgDeck *deck) {
    int unique_count = 0;
    int index = 0;
    int deck_count = valid_deck_count(deck);
    for (index = 0; index < deck_count; index += 1) {
        if (!card_seen_before(deck, index)) {
            unique_count += 1;
        }
    }
    return unique_count;
}

PTCG_API int ptcg_deck_basic_pokemon_count(const PtcgDeck *deck) {
    int count = 0;
    int index = 0;
    int deck_count = valid_deck_count(deck);
    for (index = 0; index < deck_count; index += 1) {
        if (ptcg_is_basic_pokemon_card(deck->cards[index])) {
            count += 1;
        }
    }
    return count;
}

PTCG_API int ptcg_deck_energy_count(const PtcgDeck *deck) {
    int count = 0;
    int index = 0;
    int deck_count = valid_deck_count(deck);
    for (index = 0; index < deck_count; index += 1) {
        if (ptcg_is_energy_card(deck->cards[index])) {
            count += 1;
        }
    }
    return count;
}

PTCG_API int ptcg_deck_named_counts(
    const PtcgDeck *deck,
    PtcgDeckNamedCount *out_counts,
    int max_counts
) {
    int unique_count = 0;
    int index = 0;
    int deck_count = valid_deck_count(deck);
    for (index = 0; index < deck_count; index += 1) {
        const PtcgCardCatalogEntry *entry = NULL;
        int card_id = deck->cards[index];
        int count = 0;
        if (card_seen_before(deck, index)) {
            continue;
        }
        count = ptcg_deck_count_card(deck, card_id);
        if (out_counts != NULL && unique_count < max_counts) {
            out_counts[unique_count].card_id = card_id;
            out_counts[unique_count].count = count;
            out_counts[unique_count].name[0] = '\0';
            entry = find_card_entry(card_id);
            if (entry != NULL) {
                snprintf(out_counts[unique_count].name, sizeof(out_counts[unique_count].name), "%s", entry->name);
            }
        }
        unique_count += 1;
    }
    return unique_count;
}

static unsigned int next_u32(unsigned int *state) {
    unsigned int x = *state;
    if (x == 0U) {
        x = 0x9e3779b9U;
    }
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static void shuffle_cards(int *cards, int count, unsigned int seed) {
    unsigned int state = seed == 0U ? 0x9e3779b9U : seed;
    int i = 0;
    for (i = count - 1; i > 0; i -= 1) {
        int j = (int)(next_u32(&state) % (unsigned int)(i + 1));
        int tmp = cards[i];
        cards[i] = cards[j];
        cards[j] = tmp;
    }
}

static int has_basic_pokemon_in_cards(const int *cards, int count) {
    int index = 0;
    for (index = 0; index < count; index += 1) {
        if (ptcg_is_basic_pokemon_card(cards[index])) {
            return 1;
        }
    }
    return 0;
}

static int setup_player_from_deck(
    const PtcgDeck *source,
    PtcgBattlePlayer *player,
    unsigned int seed,
    int *out_mulligan_count,
    char *message,
    int message_len
) {
    int shuffled[PTCG_DECK_SIZE];
    int attempt = 0;
    int index = 0;
    memset(player, 0, sizeof(PtcgBattlePlayer));

    if (!has_basic_pokemon_in_cards(source->cards, PTCG_DECK_SIZE)) {
        set_message(message, message_len, "deck has no Basic Pokemon for setup");
        return 15;
    }

    for (attempt = 0; attempt < 128; attempt += 1) {
        for (index = 0; index < PTCG_DECK_SIZE; index += 1) {
            shuffled[index] = source->cards[index];
        }
        shuffle_cards(
            shuffled,
            PTCG_DECK_SIZE,
            seed + ((unsigned int)attempt * 0x9e3779b9U)
        );
        if (has_basic_pokemon_in_cards(shuffled, PTCG_SETUP_HAND_SIZE)) {
            break;
        }
    }

    if (attempt >= 128) {
        set_message(message, message_len, "could not draw a Basic Pokemon opening hand");
        return 16;
    }
    if (out_mulligan_count != NULL) {
        *out_mulligan_count = attempt;
    }

    player->hand_count = PTCG_SETUP_HAND_SIZE;
    for (index = 0; index < PTCG_SETUP_HAND_SIZE; index += 1) {
        player->hand[index] = shuffled[index];
    }

    player->prize_count = PTCG_PRIZE_SIZE;
    for (index = 0; index < PTCG_PRIZE_SIZE; index += 1) {
        player->prize[index] = shuffled[PTCG_SETUP_HAND_SIZE + index];
    }

    player->deck_count = PTCG_DECK_SIZE - PTCG_SETUP_HAND_SIZE - PTCG_PRIZE_SIZE;
    for (index = 0; index < player->deck_count; index += 1) {
        player->deck[index] = shuffled[PTCG_SETUP_HAND_SIZE + PTCG_PRIZE_SIZE + index];
    }
    player->active_card_id = 0;
    player->bench_count = 0;
    return 0;
}

static int opening_hand_player_from_deck(
    const PtcgDeck *source,
    PtcgBattlePlayer *player,
    unsigned int seed,
    int *out_mulligan_count,
    char *message,
    int message_len
) {
    int shuffled[PTCG_DECK_SIZE];
    int attempt = 0;
    int index = 0;
    memset(player, 0, sizeof(PtcgBattlePlayer));

    if (!has_basic_pokemon_in_cards(source->cards, PTCG_DECK_SIZE)) {
        set_message(message, message_len, "deck has no Basic Pokemon for setup");
        return 15;
    }

    for (attempt = 0; attempt < 128; attempt += 1) {
        for (index = 0; index < PTCG_DECK_SIZE; index += 1) {
            shuffled[index] = source->cards[index];
        }
        shuffle_cards(
            shuffled,
            PTCG_DECK_SIZE,
            seed + ((unsigned int)attempt * 0x9e3779b9U)
        );
        if (has_basic_pokemon_in_cards(shuffled, PTCG_SETUP_HAND_SIZE)) {
            break;
        }
    }

    if (attempt >= 128) {
        set_message(message, message_len, "could not draw a Basic Pokemon opening hand");
        return 16;
    }
    if (out_mulligan_count != NULL) {
        *out_mulligan_count = attempt;
    }

    player->hand_count = PTCG_SETUP_HAND_SIZE;
    for (index = 0; index < PTCG_SETUP_HAND_SIZE; index += 1) {
        player->hand[index] = shuffled[index];
    }

    player->prize_count = 0;
    player->deck_count = PTCG_DECK_SIZE - PTCG_SETUP_HAND_SIZE;
    for (index = 0; index < player->deck_count; index += 1) {
        player->deck[index] = shuffled[PTCG_SETUP_HAND_SIZE + index];
    }
    player->active_card_id = 0;
    player->bench_count = 0;
    return 0;
}

static void deal_setup_prizes_to_player(PtcgBattlePlayer *player) {
    int index = 0;
    int prize_start = player->deck_count - PTCG_PRIZE_SIZE;
    for (index = 0; index < PTCG_PRIZE_SIZE; index += 1) {
        player->prize[index] = player->deck[player->deck_count - 1 - index];
    }
    player->prize_count = PTCG_PRIZE_SIZE;
    for (index = prize_start; index < player->deck_count; index += 1) {
        player->deck[index] = 0;
    }
    player->deck_count = prize_start;
}

static void initialize_battle_setup_defaults(PtcgBattleSetup *setup) {
    memset(setup, 0, sizeof(PtcgBattleSetup));
    setup->turn = 0;
    setup->first_player = -1;
    setup->current_player = 0;
    setup->setup_complete[0] = 0;
    setup->setup_complete[1] = 0;
    setup->setup_mulligans[0] = 0;
    setup->setup_mulligans[1] = 0;
    setup->setup_mulligan_draw_choices[0] = -1;
    setup->setup_mulligan_draw_choices[1] = -1;
    setup->energy_attached = 0;
    setup->retreated = 0;
    setup->supporter_played = 0;
    setup->lunar_cycle_used = 0;
    setup->stadium_played = 0;
    setup->stadium_card_id = 0;
    setup->stadium_player_index = -1;
    setup->fighting_attack_bonus = 0;
    setup->result = -1;
    setup->pending_promotion_player = -1;
    setup->pending_promotion_next_player = -1;
    setup->pending_dusk_ball_player = -1;
    setup->pending_dusk_ball_start = 0;
    setup->pending_dusk_ball_count = 0;
    setup->pending_boss_orders_player = -1;
    setup->pending_heave_ho_player = -1;
    setup->pending_fighting_gong_player = -1;
    setup->pending_poke_pad_player = -1;
    setup->pending_switch_player = -1;
    setup->pending_retreat_player = -1;
    setup->pending_retreat_remaining = 0;
    setup->pending_aura_jab_player = -1;
    setup->pending_aura_jab_remaining = 0;
}

static void copy_deck_to_pregame_player(const PtcgDeck *source, PtcgBattlePlayer *player) {
    int index = 0;
    memset(player, 0, sizeof(PtcgBattlePlayer));
    player->deck_count = source->card_count;
    for (index = 0; index < source->card_count && index < PTCG_DECK_SIZE; index += 1) {
        player->deck[index] = source->cards[index];
    }
}

static void copy_pregame_player_to_deck(const PtcgBattlePlayer *player, PtcgDeck *deck) {
    int index = 0;
    memset(deck, 0, sizeof(PtcgDeck));
    deck->card_count = player->deck_count;
    for (index = 0; index < player->deck_count && index < PTCG_DECK_SIZE; index += 1) {
        deck->cards[index] = player->deck[index];
    }
}

static int deal_setup_from_loaded_decks(
    const PtcgDeck *deck0,
    const PtcgDeck *deck1,
    unsigned int seed,
    int first_player,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int error = 0;
    int mulligans0 = 0;
    int mulligans1 = 0;

    if (first_player < 0 || first_player > 1) {
        set_message(message, message_len, "first_player must be 0 or 1");
        return 6;
    }

    initialize_battle_setup_defaults(out_setup);
    out_setup->first_player = first_player;
    out_setup->current_player = first_player;

    error = setup_player_from_deck(
        deck0,
        &out_setup->players[0],
        seed ^ 0xa511e9b3U,
        &mulligans0,
        message,
        message_len
    );
    if (error != 0) {
        return error;
    }
    error = setup_player_from_deck(
        deck1,
        &out_setup->players[1],
        seed ^ 0x63d83595U,
        &mulligans1,
        message,
        message_len
    );
    if (error != 0) {
        return error;
    }
    out_setup->setup_mulligans[0] = mulligans0;
    out_setup->setup_mulligans[1] = mulligans1;
    set_message(message, message_len, "ok");
    return 0;
}

static int deal_opening_hands_from_loaded_decks(
    const PtcgDeck *deck0,
    const PtcgDeck *deck1,
    unsigned int seed,
    int first_player,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int error = 0;
    int mulligans0 = 0;
    int mulligans1 = 0;

    if (first_player < 0 || first_player > 1) {
        set_message(message, message_len, "first_player must be 0 or 1");
        return 6;
    }

    initialize_battle_setup_defaults(out_setup);
    out_setup->first_player = first_player;
    out_setup->current_player = first_player;

    error = opening_hand_player_from_deck(
        deck0,
        &out_setup->players[0],
        seed ^ 0xa511e9b3U,
        &mulligans0,
        message,
        message_len
    );
    if (error != 0) {
        return error;
    }
    error = opening_hand_player_from_deck(
        deck1,
        &out_setup->players[1],
        seed ^ 0x63d83595U,
        &mulligans1,
        message,
        message_len
    );
    if (error != 0) {
        return error;
    }
    out_setup->setup_mulligans[0] = mulligans0;
    out_setup->setup_mulligans[1] = mulligans1;
    set_message(message, message_len, "ok");
    return 0;
}

static int draw_card_for_player(PtcgBattlePlayer *player, char *message, int message_len) {
    if (player->deck_count <= 0) {
        set_message(message, message_len, "cannot draw from an empty deck");
        return 13;
    }
    if (player->hand_count >= PTCG_HAND_SIZE) {
        set_message(message, message_len, "hand capacity exceeded");
        return 14;
    }

    player->hand[player->hand_count] = player->deck[player->deck_count - 1];
    player->hand_count += 1;
    player->deck[player->deck_count - 1] = 0;
    player->deck_count -= 1;
    return 0;
}

static int draw_up_to_for_player(PtcgBattlePlayer *player, int count, char *message, int message_len) {
    int drawn = 0;
    int error = 0;
    for (drawn = 0; drawn < count && player->deck_count > 0; drawn += 1) {
        error = draw_card_for_player(player, message, message_len);
        if (error != 0) {
            return error;
        }
    }
    set_message(message, message_len, "ok");
    return 0;
}

static int advance_turn_after_attack_effect(
    PtcgBattleSetup *setup,
    int next_player,
    char *message,
    int message_len
) {
    int error = 0;
    setup->turn += 1;
    setup->current_player = next_player;
    setup->energy_attached = 0;
    setup->retreated = 0;
    setup->supporter_played = 0;
    setup->lunar_cycle_used = 0;
    setup->fighting_attack_bonus = 0;
    error = draw_card_for_player(&setup->players[setup->current_player], message, message_len);
    if (error != 0) {
        return error;
    }
    return 0;
}

static void remove_card_from_hand(PtcgBattlePlayer *player, int hand_index) {
    int index = 0;
    for (index = hand_index; index < player->hand_count - 1; index += 1) {
        player->hand[index] = player->hand[index + 1];
    }
    player->hand[player->hand_count - 1] = 0;
    player->hand_count -= 1;
}

static void remove_card_from_discard(PtcgBattlePlayer *player, int discard_index) {
    int index = 0;
    for (index = discard_index; index < player->discard_count - 1; index += 1) {
        player->discard[index] = player->discard[index + 1];
    }
    player->discard[player->discard_count - 1] = 0;
    player->discard_count -= 1;
}

static int is_basic_fighting_energy_card(int card_id) {
    const PtcgCardCatalogEntry *entry = find_card_entry(card_id);
    if (entry == NULL) {
        return 0;
    }
    return entry->card_type == 5 && entry->energy_type == PTCG_ENERGY_FIGHTING;
}

static int count_basic_fighting_energy_in_discard(const PtcgBattlePlayer *player) {
    int index = 0;
    int count = 0;
    if (player == NULL) {
        return 0;
    }
    for (index = 0; index < player->discard_count; index += 1) {
        if (is_basic_fighting_energy_card(player->discard[index])) {
            count += 1;
        }
    }
    return count;
}

static int count_open_bench_energy_slots(const PtcgBattlePlayer *player) {
    int bench_index = 0;
    int count = 0;
    if (player == NULL) {
        return 0;
    }
    for (bench_index = 0; bench_index < player->bench_count; bench_index += 1) {
        if (player->bench_energy_count[bench_index] < PTCG_ATTACHED_SIZE) {
            count += PTCG_ATTACHED_SIZE - player->bench_energy_count[bench_index];
        }
    }
    return count;
}

static int aura_jab_attachment_limit(const PtcgBattlePlayer *player) {
    int energy_count = count_basic_fighting_energy_in_discard(player);
    int open_slots = count_open_bench_energy_slots(player);
    int limit = energy_count < open_slots ? energy_count : open_slots;
    if (limit > 3) {
        limit = 3;
    }
    return limit > 0 ? limit : 0;
}

static int aura_jab_has_legal_attachment(const PtcgBattlePlayer *player) {
    return aura_jab_attachment_limit(player) > 0;
}

static int append_attached_energy(
    PtcgBattlePlayer *player,
    int in_play_area,
    int in_play_index,
    int card_id,
    char *message,
    int message_len
) {
    if (in_play_area == PTCG_AREA_ACTIVE) {
        if (in_play_index != 0 || player->active_card_id == 0) {
            set_message(message, message_len, "Active Pokemon target is invalid");
            return 6;
        }
        if (player->active_energy_count >= PTCG_ATTACHED_SIZE) {
            set_message(message, message_len, "Active Pokemon has too many attached Energy cards");
            return 14;
        }
        player->active_energy[player->active_energy_count] = card_id;
        player->active_energy_count += 1;
        return 0;
    }
    if (in_play_area == PTCG_AREA_BENCH) {
        if (in_play_index < 0 || in_play_index >= player->bench_count) {
            set_message(message, message_len, "Bench Pokemon target is invalid");
            return 6;
        }
        if (player->bench_energy_count[in_play_index] >= PTCG_ATTACHED_SIZE) {
            set_message(message, message_len, "Bench Pokemon has too many attached Energy cards");
            return 14;
        }
        player->bench_energy[in_play_index][player->bench_energy_count[in_play_index]] = card_id;
        player->bench_energy_count[in_play_index] += 1;
        return 0;
    }

    set_message(message, message_len, "in_play_area must be Active or Bench");
    return 6;
}

static int attach_tool_card(
    PtcgBattlePlayer *player,
    int in_play_area,
    int in_play_index,
    int card_id,
    char *message,
    int message_len
) {
    if (in_play_area == PTCG_AREA_ACTIVE) {
        if (in_play_index != 0 || player->active_card_id == 0) {
            set_message(message, message_len, "Active Pokemon target is invalid");
            return 6;
        }
        if (player->active_tool_card_id != 0) {
            set_message(message, message_len, "Active Pokemon already has a Pokemon Tool attached");
            return 36;
        }
        player->active_tool_card_id = card_id;
        return 0;
    }
    if (in_play_area == PTCG_AREA_BENCH) {
        if (in_play_index < 0 || in_play_index >= player->bench_count) {
            set_message(message, message_len, "Bench Pokemon target is invalid");
            return 6;
        }
        if (player->bench_tool[in_play_index] != 0) {
            set_message(message, message_len, "Bench Pokemon already has a Pokemon Tool attached");
            return 36;
        }
        player->bench_tool[in_play_index] = card_id;
        return 0;
    }

    set_message(message, message_len, "in_play_area must be Active or Bench");
    return 6;
}

PTCG_API int ptcg_start_battle_pregame_from_csv(
    const char *deck0_path,
    const char *deck1_path,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgDeck deck0;
    PtcgDeck deck1;
    int error = 0;

    if (out_setup == NULL) {
        set_message(message, message_len, "out_setup pointer is null");
        return 5;
    }
    initialize_battle_setup_defaults(out_setup);

    error = ptcg_load_deck_csv(deck0_path, &deck0, message, message_len);
    if (error != 0) {
        return error;
    }
    error = ptcg_load_deck_csv(deck1_path, &deck1, message, message_len);
    if (error != 0) {
        return error;
    }

    copy_deck_to_pregame_player(&deck0, &out_setup->players[0]);
    copy_deck_to_pregame_player(&deck1, &out_setup->players[1]);
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_select_pregame_first_player(
    const PtcgBattleSetup *pregame,
    int first_player,
    unsigned int seed,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgDeck deck0;
    PtcgDeck deck1;

    if (pregame == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (first_player < 0 || first_player > 1) {
        set_message(message, message_len, "first_player must be 0 or 1");
        return 6;
    }
    if (pregame->turn != 0 || pregame->first_player != -1) {
        set_message(message, message_len, "battle is not waiting for first player selection");
        return 10;
    }
    if (
        pregame->players[0].deck_count != PTCG_DECK_SIZE
        || pregame->players[1].deck_count != PTCG_DECK_SIZE
        || pregame->players[0].hand_count != 0
        || pregame->players[1].hand_count != 0
        || pregame->players[0].prize_count != 0
        || pregame->players[1].prize_count != 0
    ) {
        set_message(message, message_len, "pregame decks must be untouched 60-card decks");
        return 10;
    }

    copy_pregame_player_to_deck(&pregame->players[0], &deck0);
    copy_pregame_player_to_deck(&pregame->players[1], &deck1);
    return deal_opening_hands_from_loaded_decks(
        &deck0,
        &deck1,
        seed,
        first_player,
        out_setup,
        message,
        message_len
    );
}

PTCG_API int ptcg_start_battle_setup_from_csv(
    const char *deck0_path,
    const char *deck1_path,
    unsigned int seed,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgDeck deck0;
    PtcgDeck deck1;
    int error = 0;

    if (out_setup == NULL) {
        set_message(message, message_len, "out_setup pointer is null");
        return 5;
    }

    error = ptcg_load_deck_csv(deck0_path, &deck0, message, message_len);
    if (error != 0) {
        return error;
    }
    error = ptcg_load_deck_csv(deck1_path, &deck1, message, message_len);
    if (error != 0) {
        return error;
    }
    return deal_setup_from_loaded_decks(
        &deck0,
        &deck1,
        seed,
        (int)(seed % 2U),
        out_setup,
        message,
        message_len
    );
}

PTCG_API int ptcg_select_setup_active(
    const PtcgBattleSetup *setup,
    int player_index,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (player_index < 0 || player_index > 1) {
        set_message(message, message_len, "player_index must be 0 or 1");
        return 6;
    }
    if (setup->setup_complete[player_index] != 0) {
        set_message(message, message_len, "setup player is already complete");
        return 10;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[player_index];
    if (player->active_card_id != 0) {
        set_message(message, message_len, "setup Active Pokemon is already selected");
        return 8;
    }
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (!ptcg_is_basic_pokemon_card(selected_card)) {
        set_message(message, message_len, "selected card is not a Basic Pokemon");
        return 7;
    }

    player->active_card_id = selected_card;
    player->active_damage = 0;
    player->active_entered_turn = 0;
    player->active_evolved_turn = 0;
    player->active_pre_evolution_count = 0;
    memset(player->active_pre_evolution, 0, sizeof(player->active_pre_evolution));
    clear_active_attack_lock(player);
    remove_card_from_hand(player, hand_index);
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_deal_setup_prizes(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int index = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->turn != 0 || setup->first_player < 0 || setup->first_player > 1) {
        set_message(message, message_len, "setup prizes can only be dealt during pre-battle setup");
        return 10;
    }
    for (index = 0; index < 2; index += 1) {
        if (setup->players[index].active_card_id == 0) {
            set_message(message, message_len, "both players must select Active Pokemon before prizes are dealt");
            return 8;
        }
        if (setup->players[index].prize_count != 0) {
            set_message(message, message_len, "setup prizes are already dealt");
            return 10;
        }
        if (setup->players[index].deck_count < PTCG_PRIZE_SIZE) {
            set_message(message, message_len, "not enough cards to deal setup prizes");
            return 13;
        }
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    deal_setup_prizes_to_player(&out_setup->players[0]);
    deal_setup_prizes_to_player(&out_setup->players[1]);
    out_setup->current_player = out_setup->first_player;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_select_setup_bench(
    const PtcgBattleSetup *setup,
    int player_index,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (player_index < 0 || player_index > 1) {
        set_message(message, message_len, "player_index must be 0 or 1");
        return 6;
    }
    if (setup->setup_complete[player_index] != 0) {
        set_message(message, message_len, "setup player is already complete");
        return 10;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[player_index];
    if (player->active_card_id == 0) {
        set_message(message, message_len, "Active Pokemon must be selected before setup Bench Pokemon");
        return 8;
    }
    if (player->bench_count >= PTCG_BENCH_SIZE) {
        set_message(message, message_len, "setup Bench is full");
        return 9;
    }
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (!ptcg_is_basic_pokemon_card(selected_card)) {
        set_message(message, message_len, "selected card is not a Basic Pokemon");
        return 7;
    }

    player->bench[player->bench_count] = selected_card;
    player->bench_damage[player->bench_count] = 0;
    player->bench_entered_turn[player->bench_count] = 0;
    player->bench_evolved_turn[player->bench_count] = 0;
    player->bench_pre_evolution_count[player->bench_count] = 0;
    memset(player->bench_pre_evolution[player->bench_count], 0, sizeof(player->bench_pre_evolution[player->bench_count]));
    player->bench_count += 1;
    remove_card_from_hand(player, hand_index);
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_finish_setup_player(
    const PtcgBattleSetup *setup,
    int player_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (player_index < 0 || player_index > 1) {
        set_message(message, message_len, "player_index must be 0 or 1");
        return 6;
    }
    if (setup->setup_complete[player_index] != 0) {
        set_message(message, message_len, "setup player is already complete");
        return 10;
    }
    if (setup->players[player_index].active_card_id == 0) {
        set_message(message, message_len, "Active Pokemon must be selected before finishing setup");
        return 8;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    out_setup->setup_complete[player_index] = 1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_is_setup_complete(const PtcgBattleSetup *setup) {
    if (setup == NULL) {
        return 0;
    }
    return setup->setup_complete[0] != 0 && setup->setup_complete[1] != 0;
}

PTCG_API int ptcg_begin_first_turn(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before the first turn");
        return 11;
    }
    if (setup->turn != 0) {
        set_message(message, message_len, "battle has already begun");
        return 12;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    out_setup->turn = 1;
    out_setup->current_player = out_setup->first_player;
    out_setup->energy_attached = 0;
    out_setup->retreated = 0;
    out_setup->supporter_played = 0;
    out_setup->lunar_cycle_used = 0;
    out_setup->stadium_played = 0;
    out_setup->fighting_attack_bonus = 0;
    error = draw_card_for_player(&out_setup->players[out_setup->current_player], message, message_len);
    if (error != 0) {
        return error;
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_end_turn(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before ending a turn");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    out_setup->turn += 1;
    out_setup->current_player = 1 - out_setup->current_player;
    out_setup->energy_attached = 0;
    out_setup->retreated = 0;
    out_setup->supporter_played = 0;
    out_setup->lunar_cycle_used = 0;
    out_setup->stadium_played = 0;
    out_setup->fighting_attack_bonus = 0;
    error = draw_card_for_player(&out_setup->players[out_setup->current_player], message, message_len);
    if (error != 0) {
        return error;
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_basic_to_bench(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing cards");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (player->bench_count >= PTCG_BENCH_SIZE) {
        set_message(message, message_len, "Bench is full");
        return 9;
    }
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (!ptcg_is_basic_pokemon_card(selected_card)) {
        set_message(message, message_len, "selected card is not a Basic Pokemon");
        return 7;
    }

    player->bench[player->bench_count] = selected_card;
    player->bench_damage[player->bench_count] = 0;
    player->bench_entered_turn[player->bench_count] = setup->turn;
    player->bench_evolved_turn[player->bench_count] = 0;
    player->bench_count += 1;
    remove_card_from_hand(player, hand_index);
    set_message(message, message_len, "ok");
    return 0;
}

static int can_evolve_into(const PtcgCardCatalogEntry *evolution, int source_card_id) {
    const PtcgCardCatalogEntry *source = find_card_entry(source_card_id);
    if (evolution == NULL || source == NULL) {
        return 0;
    }
    if (evolution->card_type != 0 || (evolution->stage1 == 0 && evolution->stage2 == 0)) {
        return 0;
    }
    if (evolution->evolves_from == NULL) {
        return 0;
    }
    return strcmp(evolution->evolves_from, source->name) == 0;
}

static int push_pre_evolution_card(int card_id, int *count, int *cards) {
    int index = 0;
    if (card_id <= 0) {
        return 0;
    }
    if (*count >= PTCG_PRE_EVOLUTION_SIZE) {
        return 14;
    }
    for (index = *count; index > 0; index -= 1) {
        cards[index] = cards[index - 1];
    }
    cards[0] = card_id;
    *count += 1;
    return 0;
}

static int can_evolve_target_this_turn(
    const PtcgBattleSetup *setup,
    int entered_turn,
    int evolved_turn,
    char *message,
    int message_len
) {
    if (setup->turn <= 2) {
        set_message(message, message_len, "Pokemon cannot evolve during a player's first turn");
        return 0;
    }
    if (entered_turn == setup->turn || evolved_turn == setup->turn) {
        set_message(message, message_len, "target Pokemon cannot evolve this turn");
        return 0;
    }
    return 1;
}

static void maybe_start_heave_ho_catcher(PtcgBattleSetup *setup, int evolved_card_id) {
    int opponent_index = 0;
    if (setup == NULL || evolved_card_id != PTCG_CARD_HARIYAMA) {
        return;
    }
    opponent_index = 1 - setup->current_player;
    if (opponent_index < 0 || opponent_index > 1) {
        return;
    }
    if (setup->players[opponent_index].bench_count > 0) {
        setup->pending_heave_ho_player = setup->current_player;
    }
}

PTCG_API int ptcg_evolve_from_hand(
    const PtcgBattleSetup *setup,
    int hand_index,
    int in_play_area,
    int in_play_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    const PtcgCardCatalogEntry *evolution = NULL;
    int selected_card = 0;
    int source_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before evolving");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    evolution = find_card_entry(selected_card);
    if (evolution == NULL || evolution->card_type != 0 || (evolution->stage1 == 0 && evolution->stage2 == 0)) {
        set_message(message, message_len, "selected card is not an Evolution Pokemon");
        return 23;
    }

    if (in_play_area == PTCG_AREA_ACTIVE) {
        if (in_play_index != 0 || player->active_card_id == 0) {
            set_message(message, message_len, "Active Pokemon target is invalid");
            return 6;
        }
        source_card = player->active_card_id;
        if (!can_evolve_target_this_turn(
            setup,
            player->active_entered_turn,
            player->active_evolved_turn,
            message,
            message_len
        )) {
            return 24;
        }
        if (!can_evolve_into(evolution, source_card)) {
            set_message(message, message_len, "selected Evolution does not evolve from target Pokemon");
            return 23;
        }
        error = push_pre_evolution_card(
            source_card,
            &player->active_pre_evolution_count,
            player->active_pre_evolution
        );
        if (error != 0) {
            set_message(message, message_len, "pre-evolution capacity exceeded");
            return error;
        }
        player->active_card_id = selected_card;
        player->active_evolved_turn = setup->turn;
        clear_active_attack_lock(player);
        remove_card_from_hand(player, hand_index);
        maybe_start_heave_ho_catcher(out_setup, selected_card);
        set_message(message, message_len, "ok");
        return 0;
    }

    if (in_play_area == PTCG_AREA_BENCH) {
        if (in_play_index < 0 || in_play_index >= player->bench_count) {
            set_message(message, message_len, "Bench Pokemon target is invalid");
            return 6;
        }
        source_card = player->bench[in_play_index];
        if (!can_evolve_target_this_turn(
            setup,
            player->bench_entered_turn[in_play_index],
            player->bench_evolved_turn[in_play_index],
            message,
            message_len
        )) {
            return 24;
        }
        if (!can_evolve_into(evolution, source_card)) {
            set_message(message, message_len, "selected Evolution does not evolve from target Pokemon");
            return 23;
        }
        error = push_pre_evolution_card(
            source_card,
            &player->bench_pre_evolution_count[in_play_index],
            player->bench_pre_evolution[in_play_index]
        );
        if (error != 0) {
            set_message(message, message_len, "pre-evolution capacity exceeded");
            return error;
        }
        player->bench[in_play_index] = selected_card;
        player->bench_evolved_turn[in_play_index] = setup->turn;
        remove_card_from_hand(player, hand_index);
        maybe_start_heave_ho_catcher(out_setup, selected_card);
        set_message(message, message_len, "ok");
        return 0;
    }

    set_message(message, message_len, "in_play_area must be Active or Bench");
    return 6;
}

PTCG_API int ptcg_attach_energy(
    const PtcgBattleSetup *setup,
    int hand_index,
    int in_play_area,
    int in_play_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before attaching Energy");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }    if (setup->energy_attached != 0) {
        set_message(message, message_len, "Energy has already been attached this turn");
        return 16;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (!ptcg_is_energy_card(selected_card)) {
        set_message(message, message_len, "selected card is not an Energy card");
        return 15;
    }

    error = append_attached_energy(player, in_play_area, in_play_index, selected_card, message, message_len);
    if (error != 0) {
        return error;
    }
    remove_card_from_hand(player, hand_index);
    out_setup->energy_attached = 1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_attach_heros_cape(
    const PtcgBattleSetup *setup,
    int hand_index,
    int in_play_area,
    int in_play_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before attaching Hero's Cape");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_HEROS_CAPE) {
        set_message(message, message_len, "selected card is not Hero's Cape");
        return 37;
    }

    error = attach_tool_card(player, in_play_area, in_play_index, selected_card, message, message_len);
    if (error != 0) {
        return error;
    }
    remove_card_from_hand(player, hand_index);
    set_message(message, message_len, "ok");
    return 0;
}

static void remove_prize_cards(PtcgBattlePlayer *player, int count) {
    int index = 0;
    if (count > player->prize_count) {
        count = player->prize_count;
    }
    for (index = 0; index < count; index += 1) {
        if (player->hand_count < PTCG_HAND_SIZE) {
            player->hand[player->hand_count] = player->prize[player->prize_count - 1];
            player->hand_count += 1;
        }
        player->prize[player->prize_count - 1] = 0;
        player->prize_count -= 1;
    }
}

static int append_discard_card(PtcgBattlePlayer *player, int card_id) {
    if (card_id <= 0) {
        return 0;
    }
    if (player->discard_count >= PTCG_DISCARD_SIZE) {
        return 14;
    }
    player->discard[player->discard_count] = card_id;
    player->discard_count += 1;
    return 0;
}

static int bottom_seven_start(const PtcgBattlePlayer *player) {
    if (player->deck_count <= 7) {
        return 0;
    }
    return player->deck_count - 7;
}

static void remove_card_from_deck(PtcgBattlePlayer *player, int deck_index) {
    int index = 0;
    for (index = deck_index; index < player->deck_count - 1; index += 1) {
        player->deck[index] = player->deck[index + 1];
    }
    player->deck[player->deck_count - 1] = 0;
    player->deck_count -= 1;
}

static int is_fighting_gong_target(int card_id) {
    const PtcgCardCatalogEntry *entry = find_card_entry(card_id);
    if (entry == NULL) {
        return 0;
    }
    if (entry->card_type == 5 && entry->energy_type == PTCG_ENERGY_FIGHTING) {
        return 1;
    }
    return entry->card_type == 0 && entry->basic != 0 && entry->energy_type == PTCG_ENERGY_FIGHTING;
}

static int is_poke_pad_target(int card_id) {
    const PtcgCardCatalogEntry *entry = find_card_entry(card_id);
    if (entry == NULL) {
        return 0;
    }
    return entry->card_type == 0 && entry->ex == 0 && entry->mega_ex == 0;
}

static unsigned int dusk_ball_shuffle_seed(
    const PtcgBattleSetup *setup,
    int selected_card,
    int deck_index
) {
    unsigned int seed = 0x51f15eEDU;
    seed ^= (unsigned int)(setup->turn * 1103515245U);
    seed ^= (unsigned int)(setup->current_player * 2654435761U);
    seed ^= (unsigned int)(selected_card * 40503U);
    seed ^= (unsigned int)(deck_index * 7919U);
    return seed;
}

static unsigned int fighting_gong_shuffle_seed(
    const PtcgBattleSetup *setup,
    int selected_card,
    int deck_index
) {
    unsigned int seed = 0xf19a7116U;
    seed ^= (unsigned int)(setup->turn * 1103515245U);
    seed ^= (unsigned int)(setup->current_player * 2654435761U);
    seed ^= (unsigned int)(selected_card * 40503U);
    seed ^= (unsigned int)(deck_index * 7919U);
    return seed;
}

static unsigned int poke_pad_shuffle_seed(
    const PtcgBattleSetup *setup,
    int selected_card,
    int deck_index
) {
    unsigned int seed = 0x1152C0DEU;
    seed ^= (unsigned int)(setup->turn * 1103515245U);
    seed ^= (unsigned int)(setup->current_player * 2654435761U);
    seed ^= (unsigned int)(selected_card * 2246822519U);
    seed ^= (unsigned int)(deck_index * 3266489917U);
    return seed;
}

static unsigned int lillies_determination_shuffle_seed(
    const PtcgBattleSetup *setup,
    int hand_index,
    int hand_count
) {
    unsigned int seed = 0x1A11E55U;
    seed ^= (unsigned int)(setup->turn * 1103515245U);
    seed ^= (unsigned int)(setup->current_player * 2654435761U);
    seed ^= (unsigned int)(hand_index * 7919U);
    seed ^= (unsigned int)(hand_count * 40503U);
    return seed;
}

PTCG_API int ptcg_play_dusk_ball(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Dusk Ball");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_DUSK_BALL) {
        set_message(message, message_len, "selected card is not Dusk Ball");
        return 25;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);
    out_setup->pending_dusk_ball_player = out_setup->current_player;
    out_setup->pending_dusk_ball_start = bottom_seven_start(player);
    out_setup->pending_dusk_ball_count = player->deck_count - out_setup->pending_dusk_ball_start;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_dusk_ball(
    const PtcgBattleSetup *setup,
    int deck_index,
    int reveal,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    const PtcgCardCatalogEntry *selected_entry = NULL;
    int selected_card = 0;
    int start = 0;
    int end = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_dusk_ball_player < 0 || setup->pending_dusk_ball_player > 1) {
        set_message(message, message_len, "no pending Dusk Ball search to resolve");
        return 27;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->pending_dusk_ball_player];
    start = out_setup->pending_dusk_ball_start;
    end = start + out_setup->pending_dusk_ball_count;
    if (end > player->deck_count) {
        end = player->deck_count;
    }

    if (reveal != 0) {
        if (deck_index < start || deck_index >= end) {
            set_message(message, message_len, "Dusk Ball target must be in the bottom 7 cards");
            return 6;
        }
        selected_card = player->deck[deck_index];
        selected_entry = find_card_entry(selected_card);
        if (selected_entry == NULL || selected_entry->card_type != 0) {
            set_message(message, message_len, "Dusk Ball target is not a Pokemon");
            return 25;
        }
        if (player->hand_count >= PTCG_HAND_SIZE) {
            set_message(message, message_len, "hand capacity exceeded");
            return 14;
        }
        remove_card_from_deck(player, deck_index);
        player->hand[player->hand_count] = selected_card;
        player->hand_count += 1;
    }

    out_setup->pending_dusk_ball_player = -1;
    out_setup->pending_dusk_ball_start = 0;
    out_setup->pending_dusk_ball_count = 0;
    if (player->deck_count > 1) {
        shuffle_cards(
            player->deck,
            player->deck_count,
            dusk_ball_shuffle_seed(setup, selected_card, deck_index)
        );
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_fighting_gong(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Fighting Gong");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_FIGHTING_GONG) {
        set_message(message, message_len, "selected card is not Fighting Gong");
        return 25;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);
    out_setup->pending_fighting_gong_player = out_setup->current_player;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_premium_power_pro(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Premium Power Pro");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_PREMIUM_POWER_PRO) {
        set_message(message, message_len, "selected card is not Premium Power Pro");
        return 25;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);
    out_setup->fighting_attack_bonus += 30;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_use_lunar_cycle(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before using Lunar Cycle");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    if (setup->lunar_cycle_used != 0) {
        set_message(message, message_len, "Lunar Cycle has already been used this turn");
        return 41;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (!player_has_card_in_play(player, PTCG_CARD_LUNATONE)) {
        set_message(message, message_len, "Lunatone is not in play");
        return 42;
    }
    if (!player_has_card_in_play(player, PTCG_CARD_SOLROCK)) {
        set_message(message, message_len, "Solrock is not in play");
        return 43;
    }
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_ENERGY_FIGHTING) {
        set_message(message, message_len, "selected card is not a Basic Fighting Energy");
        return 15;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);
    error = draw_up_to_for_player(player, 3, message, message_len);
    if (error != 0) {
        return error;
    }
    out_setup->lunar_cycle_used = 1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_fighting_gong(
    const PtcgBattleSetup *setup,
    int deck_index,
    int reveal,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_fighting_gong_player < 0 || setup->pending_fighting_gong_player > 1) {
        set_message(message, message_len, "no pending Fighting Gong search to resolve");
        return 31;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->pending_fighting_gong_player];

    if (reveal != 0) {
        if (deck_index < 0 || deck_index >= player->deck_count) {
            set_message(message, message_len, "Fighting Gong target must be in the deck");
            return 6;
        }
        selected_card = player->deck[deck_index];
        if (!is_fighting_gong_target(selected_card)) {
            set_message(message, message_len, "Fighting Gong target is not a Basic Fighting Energy or Basic Fighting Pokemon");
            return 25;
        }
        if (player->hand_count >= PTCG_HAND_SIZE) {
            set_message(message, message_len, "hand capacity exceeded");
            return 14;
        }
        remove_card_from_deck(player, deck_index);
        player->hand[player->hand_count] = selected_card;
        player->hand_count += 1;
    }

    out_setup->pending_fighting_gong_player = -1;
    if (player->deck_count > 1) {
        shuffle_cards(
            player->deck,
            player->deck_count,
            fighting_gong_shuffle_seed(setup, selected_card, deck_index)
        );
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_poke_pad(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Poke Pad");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_POKE_PAD) {
        set_message(message, message_len, "selected card is not Poke Pad");
        return 25;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);
    out_setup->pending_poke_pad_player = out_setup->current_player;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_poke_pad(
    const PtcgBattleSetup *setup,
    int deck_index,
    int reveal,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_poke_pad_player < 0 || setup->pending_poke_pad_player > 1) {
        set_message(message, message_len, "no pending Poke Pad search to resolve");
        return 32;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->pending_poke_pad_player];

    if (reveal != 0) {
        if (deck_index < 0 || deck_index >= player->deck_count) {
            set_message(message, message_len, "Poke Pad target must be in the deck");
            return 6;
        }
        selected_card = player->deck[deck_index];
        if (!is_poke_pad_target(selected_card)) {
            set_message(message, message_len, "Poke Pad target is not a non-rulebox Pokemon");
            return 25;
        }
        if (player->hand_count >= PTCG_HAND_SIZE) {
            set_message(message, message_len, "hand capacity exceeded");
            return 14;
        }
        remove_card_from_deck(player, deck_index);
        player->hand[player->hand_count] = selected_card;
        player->hand_count += 1;
    }

    out_setup->pending_poke_pad_player = -1;
    if (player->deck_count > 1) {
        shuffle_cards(
            player->deck,
            player->deck_count,
            poke_pad_shuffle_seed(setup, selected_card, deck_index)
        );
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_lillies_determination(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int remaining_hand_count = 0;
    int index = 0;
    int draw_count = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Lillie's Determination");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    if (setup->supporter_played != 0) {
        set_message(message, message_len, "Supporter has already been played this turn");
        return 27;
    }
    if (is_first_players_first_turn(setup)) {
        set_message(message, message_len, "Supporter cannot be played during the first player's first turn");
        return 44;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_LILLIES_DETERMINATION) {
        set_message(message, message_len, "selected card is not Lillie's Determination");
        return 28;
    }
    if (player->deck_count + player->hand_count - 1 > PTCG_DECK_SIZE) {
        set_message(message, message_len, "deck capacity exceeded");
        return 14;
    }

    remove_card_from_hand(player, hand_index);
    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }

    remaining_hand_count = player->hand_count;
    for (index = 0; index < remaining_hand_count; index += 1) {
        player->deck[player->deck_count + index] = player->hand[index];
        player->hand[index] = 0;
    }
    player->deck_count += remaining_hand_count;
    player->hand_count = 0;

    if (player->deck_count > 1) {
        shuffle_cards(
            player->deck,
            player->deck_count,
            lillies_determination_shuffle_seed(setup, hand_index, remaining_hand_count)
        );
    }

    draw_count = player->prize_count == PTCG_PRIZE_SIZE ? 8 : 6;
    error = draw_up_to_for_player(player, draw_count, message, message_len);
    if (error != 0) {
        return error;
    }
    out_setup->supporter_played = 1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_carmine(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int remaining_hand_count = 0;
    int index = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Carmine");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    if (setup->supporter_played != 0) {
        set_message(message, message_len, "Supporter has already been played this turn");
        return 27;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }
    if (player->discard_count + player->hand_count > PTCG_DISCARD_SIZE) {
        set_message(message, message_len, "discard capacity exceeded");
        return 14;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_CARMINE) {
        set_message(message, message_len, "selected card is not Carmine");
        return 28;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);

    remaining_hand_count = player->hand_count;
    for (index = 0; index < remaining_hand_count; index += 1) {
        error = append_discard_card(player, player->hand[index]);
        if (error != 0) {
            set_message(message, message_len, "discard capacity exceeded");
            return error;
        }
        player->hand[index] = 0;
    }
    player->hand_count = 0;

    error = draw_up_to_for_player(player, 5, message, message_len);
    if (error != 0) {
        return error;
    }
    out_setup->supporter_played = 1;
    set_message(message, message_len, "ok");
    return 0;
}

static void swap_active_with_bench(PtcgBattlePlayer *player, int bench_index) {
    int active_card_id = player->active_card_id;
    int active_damage = player->active_damage;
    int active_entered_turn = player->active_entered_turn;
    int active_evolved_turn = player->active_evolved_turn;
    int active_pre_evolution_count = player->active_pre_evolution_count;
    int active_pre_evolution[PTCG_PRE_EVOLUTION_SIZE];
    int active_energy_count = player->active_energy_count;
    int active_energy[PTCG_ATTACHED_SIZE];
    int active_tool_card_id = player->active_tool_card_id;
    int index = 0;

    memset(active_pre_evolution, 0, sizeof(active_pre_evolution));
    memset(active_energy, 0, sizeof(active_energy));
    for (index = 0; index < active_pre_evolution_count; index += 1) {
        active_pre_evolution[index] = player->active_pre_evolution[index];
    }
    for (index = 0; index < active_energy_count; index += 1) {
        active_energy[index] = player->active_energy[index];
    }

    player->active_card_id = player->bench[bench_index];
    player->active_damage = player->bench_damage[bench_index];
    player->active_entered_turn = player->bench_entered_turn[bench_index];
    player->active_evolved_turn = player->bench_evolved_turn[bench_index];
    player->active_pre_evolution_count = player->bench_pre_evolution_count[bench_index];
    memset(player->active_pre_evolution, 0, sizeof(player->active_pre_evolution));
    for (index = 0; index < player->active_pre_evolution_count; index += 1) {
        player->active_pre_evolution[index] = player->bench_pre_evolution[bench_index][index];
    }
    player->active_energy_count = player->bench_energy_count[bench_index];
    memset(player->active_energy, 0, sizeof(player->active_energy));
    for (index = 0; index < player->active_energy_count; index += 1) {
        player->active_energy[index] = player->bench_energy[bench_index][index];
    }
    player->active_tool_card_id = player->bench_tool[bench_index];
    clear_active_attack_lock(player);

    player->bench[bench_index] = active_card_id;
    player->bench_damage[bench_index] = active_damage;
    player->bench_entered_turn[bench_index] = active_entered_turn;
    player->bench_evolved_turn[bench_index] = active_evolved_turn;
    player->bench_pre_evolution_count[bench_index] = active_pre_evolution_count;
    memset(player->bench_pre_evolution[bench_index], 0, sizeof(player->bench_pre_evolution[bench_index]));
    for (index = 0; index < active_pre_evolution_count; index += 1) {
        player->bench_pre_evolution[bench_index][index] = active_pre_evolution[index];
    }
    player->bench_energy_count[bench_index] = active_energy_count;
    memset(player->bench_energy[bench_index], 0, sizeof(player->bench_energy[bench_index]));
    for (index = 0; index < active_energy_count; index += 1) {
        player->bench_energy[bench_index][index] = active_energy[index];
    }
    player->bench_tool[bench_index] = active_tool_card_id;
}

PTCG_API int ptcg_play_switch(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Switch");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (player->bench_count <= 0) {
        set_message(message, message_len, "Switch requires a Benched Pokemon");
        return 6;
    }
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_SWITCH) {
        set_message(message, message_len, "selected card is not Switch");
        return 7;
    }

    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_card_from_hand(player, hand_index);
    out_setup->pending_switch_player = out_setup->current_player;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_switch(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_switch_player < 0 || setup->pending_switch_player > 1) {
        set_message(message, message_len, "no pending Switch target to resolve");
        return 33;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->pending_switch_player];
    if (bench_index < 0 || bench_index >= player->bench_count) {
        set_message(message, message_len, "bench_index is outside the current Bench");
        return 6;
    }

    swap_active_with_bench(player, bench_index);
    out_setup->pending_switch_player = -1;
    set_message(message, message_len, "ok");
    return 0;
}

static void remove_active_energy_at(PtcgBattlePlayer *player, int energy_index) {
    int index = 0;
    for (index = energy_index; index < player->active_energy_count - 1; index += 1) {
        player->active_energy[index] = player->active_energy[index + 1];
    }
    player->active_energy[player->active_energy_count - 1] = 0;
    player->active_energy_count -= 1;
}

PTCG_API int ptcg_start_retreat(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    const PtcgCardCatalogEntry *active_card = NULL;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before retreating");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    if (setup->retreated != 0) {
        set_message(message, message_len, "player already retreated this turn");
        return 37;
    }

    player = (PtcgBattlePlayer *)&setup->players[setup->current_player];
    if (player->active_card_id == 0) {
        set_message(message, message_len, "retreating player has no Active Pokemon");
        return 17;
    }
    if (player->bench_count <= 0) {
        set_message(message, message_len, "retreating player has no Benched Pokemon");
        return 6;
    }
    active_card = find_card_entry(player->active_card_id);
    if (active_card == NULL) {
        set_message(message, message_len, "unknown Active Pokemon");
        return 1;
    }
    if (player->active_energy_count < active_card->retreat_cost) {
        set_message(message, message_len, "not enough Energy to retreat");
        return 20;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    out_setup->retreated = 1;
    out_setup->pending_retreat_player = out_setup->current_player;
    out_setup->pending_retreat_remaining = active_card->retreat_cost;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_retreat_discard(
    const PtcgBattleSetup *setup,
    int energy_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_retreat_player < 0 || setup->pending_retreat_player > 1) {
        set_message(message, message_len, "player does not have a pending Retreat");
        return 38;
    }
    if (setup->pending_retreat_remaining <= 0) {
        set_message(message, message_len, "Retreat cost has already been paid");
        return 38;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->pending_retreat_player];
    if (energy_index < 0 || energy_index >= player->active_energy_count) {
        set_message(message, message_len, "energy_index is outside the Active Energy cards");
        return 6;
    }

    selected_card = player->active_energy[energy_index];
    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    remove_active_energy_at(player, energy_index);
    out_setup->pending_retreat_remaining -= 1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_retreat_promote(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_retreat_player < 0 || setup->pending_retreat_player > 1) {
        set_message(message, message_len, "player does not have a pending Retreat");
        return 38;
    }
    if (setup->pending_retreat_remaining > 0) {
        set_message(message, message_len, "Retreat cost must be paid before promotion");
        return 38;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->pending_retreat_player];
    if (bench_index < 0 || bench_index >= player->bench_count) {
        set_message(message, message_len, "bench_index is outside the current Bench");
        return 6;
    }

    swap_active_with_bench(player, bench_index);
    out_setup->pending_retreat_player = -1;
    out_setup->pending_retreat_remaining = 0;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_play_boss_orders(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    PtcgBattlePlayer *opponent = NULL;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing Boss's Orders");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    if (setup->supporter_played != 0) {
        set_message(message, message_len, "Supporter has already been played this turn");
        return 27;
    }
    if (is_first_players_first_turn(setup)) {
        set_message(message, message_len, "Supporter cannot be played during the first player's first turn");
        return 44;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    opponent = &out_setup->players[1 - out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }
    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_BOSS_ORDERS) {
        set_message(message, message_len, "selected card is not Boss's Orders");
        return 28;
    }
    if (opponent->bench_count <= 0) {
        set_message(message, message_len, "opponent has no Benched Pokemon");
        return 30;
    }

    remove_card_from_hand(player, hand_index);
    error = append_discard_card(player, selected_card);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    out_setup->supporter_played = 1;
    out_setup->pending_boss_orders_player = out_setup->current_player;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_boss_orders(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *opponent = NULL;
    int target_player = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_boss_orders_player < 0 || setup->pending_boss_orders_player > 1) {
        set_message(message, message_len, "no pending Boss's Orders target to resolve");
        return 29;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    target_player = 1 - out_setup->pending_boss_orders_player;
    opponent = &out_setup->players[target_player];
    if (bench_index < 0 || bench_index >= opponent->bench_count) {
        set_message(message, message_len, "bench_index is outside the opponent Bench");
        return 6;
    }

    swap_active_with_bench(opponent, bench_index);
    out_setup->pending_boss_orders_player = -1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_resolve_heave_ho_catcher(
    const PtcgBattleSetup *setup,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *opponent = NULL;
    int target_player = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_heave_ho_player < 0 || setup->pending_heave_ho_player > 1) {
        set_message(message, message_len, "no pending Heave-Ho Catcher target to resolve");
        return 35;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    target_player = 1 - out_setup->pending_heave_ho_player;
    opponent = &out_setup->players[target_player];
    if (bench_index < 0 || bench_index >= opponent->bench_count) {
        set_message(message, message_len, "bench_index is outside the opponent Bench");
        return 6;
    }

    swap_active_with_bench(opponent, bench_index);
    out_setup->pending_heave_ho_player = -1;
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_skip_heave_ho_catcher(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->pending_heave_ho_player < 0 || setup->pending_heave_ho_player > 1) {
        set_message(message, message_len, "no pending Heave-Ho Catcher target to resolve");
        return 35;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    out_setup->pending_heave_ho_player = -1;
    set_message(message, message_len, "ok");
    return 0;
}

static int discard_active_pokemon(PtcgBattlePlayer *player) {
    int index = 0;
    int error = 0;

    error = append_discard_card(player, player->active_card_id);
    if (error != 0) {
        return error;
    }
    for (index = 0; index < player->active_pre_evolution_count; index += 1) {
        error = append_discard_card(player, player->active_pre_evolution[index]);
        if (error != 0) {
            return error;
        }
    }
    for (index = 0; index < player->active_energy_count; index += 1) {
        error = append_discard_card(player, player->active_energy[index]);
        if (error != 0) {
            return error;
        }
    }
    error = append_discard_card(player, player->active_tool_card_id);
    if (error != 0) {
        return error;
    }
    player->active_card_id = 0;
    player->active_damage = 0;
    player->active_entered_turn = 0;
    player->active_evolved_turn = 0;
    player->active_pre_evolution_count = 0;
    memset(player->active_pre_evolution, 0, sizeof(player->active_pre_evolution));
    player->active_energy_count = 0;
    memset(player->active_energy, 0, sizeof(player->active_energy));
    player->active_tool_card_id = 0;
    clear_active_attack_lock(player);
    return 0;
}

static int prize_value_for_card(const PtcgCardCatalogEntry *card) {
    if (card == NULL) {
        return 1;
    }
    if (card->mega_ex != 0) {
        return 3;
    }
    if (card->ex != 0) {
        return 2;
    }
    return 1;
}

static void promote_bench_to_active(PtcgBattlePlayer *player, int bench_index) {
    int index = 0;
    int energy_index = 0;
    if (bench_index < 0 || bench_index >= player->bench_count) {
        player->active_card_id = 0;
        player->active_damage = 0;
        player->active_entered_turn = 0;
        player->active_evolved_turn = 0;
        player->active_pre_evolution_count = 0;
        memset(player->active_pre_evolution, 0, sizeof(player->active_pre_evolution));
        player->active_energy_count = 0;
        memset(player->active_energy, 0, sizeof(player->active_energy));
        player->active_tool_card_id = 0;
        clear_active_attack_lock(player);
        return;
    }

    player->active_card_id = player->bench[bench_index];
    player->active_damage = player->bench_damage[bench_index];
    player->active_entered_turn = player->bench_entered_turn[bench_index];
    player->active_evolved_turn = player->bench_evolved_turn[bench_index];
    player->active_pre_evolution_count = player->bench_pre_evolution_count[bench_index];
    memset(player->active_pre_evolution, 0, sizeof(player->active_pre_evolution));
    for (energy_index = 0; energy_index < player->active_pre_evolution_count; energy_index += 1) {
        player->active_pre_evolution[energy_index] = player->bench_pre_evolution[bench_index][energy_index];
    }
    player->active_energy_count = player->bench_energy_count[bench_index];
    memset(player->active_energy, 0, sizeof(player->active_energy));
    for (energy_index = 0; energy_index < player->active_energy_count; energy_index += 1) {
        player->active_energy[energy_index] = player->bench_energy[bench_index][energy_index];
    }
    player->active_tool_card_id = player->bench_tool[bench_index];
    clear_active_attack_lock(player);

    for (index = bench_index; index < player->bench_count - 1; index += 1) {
        player->bench[index] = player->bench[index + 1];
        player->bench_damage[index] = player->bench_damage[index + 1];
        player->bench_entered_turn[index] = player->bench_entered_turn[index + 1];
        player->bench_evolved_turn[index] = player->bench_evolved_turn[index + 1];
        player->bench_pre_evolution_count[index] = player->bench_pre_evolution_count[index + 1];
        memset(player->bench_pre_evolution[index], 0, sizeof(player->bench_pre_evolution[index]));
        for (energy_index = 0; energy_index < player->bench_pre_evolution_count[index]; energy_index += 1) {
            player->bench_pre_evolution[index][energy_index] = player->bench_pre_evolution[index + 1][energy_index];
        }
        player->bench_energy_count[index] = player->bench_energy_count[index + 1];
        memset(player->bench_energy[index], 0, sizeof(player->bench_energy[index]));
        for (energy_index = 0; energy_index < player->bench_energy_count[index]; energy_index += 1) {
            player->bench_energy[index][energy_index] = player->bench_energy[index + 1][energy_index];
        }
        player->bench_tool[index] = player->bench_tool[index + 1];
    }

    player->bench_count -= 1;
    player->bench[player->bench_count] = 0;
    player->bench_damage[player->bench_count] = 0;
    player->bench_entered_turn[player->bench_count] = 0;
    player->bench_evolved_turn[player->bench_count] = 0;
    player->bench_pre_evolution_count[player->bench_count] = 0;
    memset(player->bench_pre_evolution[player->bench_count], 0, sizeof(player->bench_pre_evolution[player->bench_count]));
    player->bench_energy_count[player->bench_count] = 0;
    memset(player->bench_energy[player->bench_count], 0, sizeof(player->bench_energy[player->bench_count]));
    player->bench_tool[player->bench_count] = 0;
}

static int resolve_active_knockout(
    PtcgBattleSetup *setup,
    int knocked_player,
    int prize_player,
    int next_player_after_promotion,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *knocked = NULL;
    PtcgBattlePlayer *prize_taker = NULL;
    const PtcgCardCatalogEntry *knocked_card = NULL;
    int prize_value = 0;
    int error = 0;

    if (setup == NULL || knocked_player < 0 || knocked_player > 1 || prize_player < 0 || prize_player > 1) {
        return 0;
    }
    knocked = &setup->players[knocked_player];
    if (knocked->active_card_id == 0) {
        return 0;
    }
    knocked_card = find_card_entry(knocked->active_card_id);
    if (
        knocked_card == NULL
        || effective_hp_for_card(knocked_card, knocked->active_tool_card_id, setup->stadium_card_id) <= 0
        || knocked->active_damage < effective_hp_for_card(knocked_card, knocked->active_tool_card_id, setup->stadium_card_id)
    ) {
        return 0;
    }

    prize_taker = &setup->players[prize_player];
    prize_value = prize_value_for_card(knocked_card);
    remove_prize_cards(prize_taker, prize_value);
    if (prize_taker->prize_count <= 0) {
        setup->result = prize_player;
    }
    error = discard_active_pokemon(knocked);
    if (error != 0) {
        set_message(message, message_len, "discard capacity exceeded");
        return error;
    }
    if (setup->result < 0) {
        if (knocked->bench_count <= 0) {
            setup->result = prize_player;
        } else if (knocked->bench_count == 1) {
            promote_bench_to_active(knocked, 0);
        } else {
            if (next_player_after_promotion < 0 || next_player_after_promotion > 1) {
                next_player_after_promotion = knocked_player;
            }
            setup->pending_promotion_player = knocked_player;
            setup->pending_promotion_next_player = next_player_after_promotion;
            setup->current_player = knocked_player;
        }
    }
    return 0;
}

static int resolve_stadium_knockouts(
    PtcgBattleSetup *setup,
    int next_player_after_promotion,
    char *message,
    int message_len
) {
    int first_knocked_player = 0;
    int second_knocked_player = 0;
    int error = 0;

    if (setup == NULL) {
        return 0;
    }

    first_knocked_player = 1 - setup->current_player;
    second_knocked_player = setup->current_player;

    error = resolve_active_knockout(
        setup,
        first_knocked_player,
        1 - first_knocked_player,
        next_player_after_promotion,
        message,
        message_len
    );
    if (error != 0 || setup->result >= 0 || setup->pending_promotion_player >= 0) {
        return error;
    }

    return resolve_active_knockout(
        setup,
        second_knocked_player,
        1 - second_knocked_player,
        next_player_after_promotion,
        message,
        message_len
    );
}

PTCG_API int ptcg_play_gravity_mountain(
    const PtcgBattleSetup *setup,
    int hand_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *player = NULL;
    int selected_card = 0;
    int old_stadium_card_id = 0;
    int old_stadium_player_index = -1;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before playing a Stadium");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    if (setup->stadium_played != 0) {
        set_message(message, message_len, "Stadium has already been played this turn");
        return 38;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[out_setup->current_player];
    if (hand_index < 0 || hand_index >= player->hand_count) {
        set_message(message, message_len, "hand_index is outside the current hand");
        return 6;
    }

    selected_card = player->hand[hand_index];
    if (selected_card != PTCG_CARD_GRAVITY_MOUNTAIN) {
        set_message(message, message_len, "selected card is not Gravity Mountain");
        return 40;
    }
    if (out_setup->stadium_card_id == selected_card) {
        set_message(message, message_len, "Gravity Mountain is already in play");
        return 39;
    }

    old_stadium_card_id = out_setup->stadium_card_id;
    old_stadium_player_index = out_setup->stadium_player_index;
    if (old_stadium_card_id != 0 && old_stadium_player_index >= 0 && old_stadium_player_index <= 1) {
        error = append_discard_card(&out_setup->players[old_stadium_player_index], old_stadium_card_id);
        if (error != 0) {
            set_message(message, message_len, "discard capacity exceeded");
            return error;
        }
    }

    out_setup->stadium_card_id = selected_card;
    out_setup->stadium_player_index = out_setup->current_player;
    out_setup->stadium_played = 1;
    remove_card_from_hand(player, hand_index);
    error = resolve_stadium_knockouts(out_setup, out_setup->current_player, message, message_len);
    if (error != 0) {
        return error;
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_promote_bench_to_active(
    const PtcgBattleSetup *setup,
    int player_index,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int error = 0;
    int next_player = player_index;
    PtcgBattlePlayer *player = NULL;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (player_index < 0 || player_index > 1) {
        set_message(message, message_len, "player_index must be 0 or 1");
        return 6;
    }
    if (setup->pending_promotion_player != player_index) {
        set_message(message, message_len, "player does not have a pending Active promotion");
        return 22;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (bench_index < 0 || bench_index >= setup->players[player_index].bench_count) {
        set_message(message, message_len, "bench_index is outside the current Bench");
        return 6;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    if (setup->pending_promotion_next_player >= 0 && setup->pending_promotion_next_player <= 1) {
        next_player = setup->pending_promotion_next_player;
    }
    player = &out_setup->players[player_index];
    promote_bench_to_active(player, bench_index);
    out_setup->pending_promotion_player = -1;
    out_setup->pending_promotion_next_player = -1;
    out_setup->turn += 1;
    out_setup->current_player = next_player;
    out_setup->energy_attached = 0;
    out_setup->retreated = 0;
    out_setup->supporter_played = 0;
    out_setup->lunar_cycle_used = 0;
    out_setup->fighting_attack_bonus = 0;
    error = draw_card_for_player(&out_setup->players[out_setup->current_player], message, message_len);
    if (error != 0) {
        return error;
    }
    set_message(message, message_len, "ok");
    return 0;
}

static void maybe_start_aura_jab(
    PtcgBattleSetup *setup,
    int attack_id,
    int attacking_player
) {
    int remaining = 0;
    if (setup == NULL || attack_id != PTCG_ATTACK_AURA_JAB) {
        return;
    }
    if (setup->result >= 0 || setup->pending_promotion_player >= 0) {
        return;
    }
    if (attacking_player < 0 || attacking_player > 1) {
        return;
    }
    remaining = aura_jab_attachment_limit(&setup->players[attacking_player]);
    if (remaining <= 0) {
        return;
    }
    setup->pending_aura_jab_player = attacking_player;
    setup->pending_aura_jab_remaining = remaining;
    setup->current_player = attacking_player;
}

PTCG_API int ptcg_resolve_aura_jab_attach(
    const PtcgBattleSetup *setup,
    int discard_index,
    int bench_index,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    const PtcgBattlePlayer *source_player = NULL;
    PtcgBattlePlayer *player = NULL;
    int player_index = 0;
    int selected_card = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_aura_jab_player < 0 || setup->pending_aura_jab_player > 1) {
        set_message(message, message_len, "player does not have pending Aura Jab attachments");
        return 36;
    }
    if (setup->pending_aura_jab_remaining <= 0) {
        set_message(message, message_len, "Aura Jab has no remaining attachments");
        return 36;
    }
    player_index = setup->pending_aura_jab_player;
    source_player = &setup->players[player_index];
    if (discard_index < 0 || discard_index >= source_player->discard_count) {
        set_message(message, message_len, "discard_index is outside the current discard pile");
        return 6;
    }
    selected_card = source_player->discard[discard_index];
    if (!is_basic_fighting_energy_card(selected_card)) {
        set_message(message, message_len, "selected discard card is not a Basic Fighting Energy");
        return 7;
    }
    if (bench_index < 0 || bench_index >= source_player->bench_count) {
        set_message(message, message_len, "Bench Pokemon target is invalid");
        return 6;
    }
    if (source_player->bench_energy_count[bench_index] >= PTCG_ATTACHED_SIZE) {
        set_message(message, message_len, "Bench Pokemon has too many attached Energy cards");
        return 14;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player = &out_setup->players[player_index];
    error = append_attached_energy(
        player,
        PTCG_AREA_BENCH,
        bench_index,
        selected_card,
        message,
        message_len
    );
    if (error != 0) {
        return error;
    }
    remove_card_from_discard(player, discard_index);
    out_setup->pending_aura_jab_remaining -= 1;
    if (
        out_setup->pending_aura_jab_remaining <= 0
        || !aura_jab_has_legal_attachment(player)
    ) {
        out_setup->pending_aura_jab_player = -1;
        out_setup->pending_aura_jab_remaining = 0;
        error = advance_turn_after_attack_effect(out_setup, 1 - player_index, message, message_len);
        if (error != 0) {
            return error;
        }
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_skip_aura_jab(
    const PtcgBattleSetup *setup,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    int player_index = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_aura_jab_player < 0 || setup->pending_aura_jab_player > 1) {
        set_message(message, message_len, "player does not have pending Aura Jab attachments");
        return 36;
    }

    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    player_index = out_setup->pending_aura_jab_player;
    out_setup->pending_aura_jab_player = -1;
    out_setup->pending_aura_jab_remaining = 0;
    error = advance_turn_after_attack_effect(out_setup, 1 - player_index, message, message_len);
    if (error != 0) {
        return error;
    }
    set_message(message, message_len, "ok");
    return 0;
}

PTCG_API int ptcg_use_attack(
    const PtcgBattleSetup *setup,
    int attack_id,
    PtcgBattleSetup *out_setup,
    char *message,
    int message_len
) {
    PtcgBattlePlayer *attacker = NULL;
    PtcgBattlePlayer *defender = NULL;
    const PtcgCardCatalogEntry *attacking_card = NULL;
    const PtcgCardCatalogEntry *defending_card = NULL;
    const PtcgAttackCatalogEntry *attack = NULL;
    int attacking_player = 0;
    int defending_player = 0;
    int damage = 0;
    int self_damage = 0;
    int error = 0;

    if (setup == NULL || out_setup == NULL) {
        set_message(message, message_len, "setup pointer is null");
        return 5;
    }
    if (!ptcg_is_setup_complete(setup)) {
        set_message(message, message_len, "both players must finish setup before attacking");
        return 11;
    }
    if (setup->turn <= 0) {
        set_message(message, message_len, "battle has not begun");
        return 12;
    }
    if (setup->result >= 0) {
        set_message(message, message_len, "battle has already ended");
        return 3;
    }
    if (setup->pending_promotion_player >= 0) {
        set_message(message, message_len, "pending Active promotion must be resolved");
        return 21;
    }
    if (setup->pending_dusk_ball_player >= 0) {
        set_message(message, message_len, "pending Dusk Ball search must be resolved");
        return 26;
    }
    if (setup->pending_boss_orders_player >= 0) {
        set_message(message, message_len, "pending Boss's Orders target must be resolved");
        return 29;
    }
    if (setup->pending_heave_ho_player >= 0) {
        set_message(message, message_len, "pending Heave-Ho Catcher target must be resolved");
        return 35;
    }
    if (setup->pending_fighting_gong_player >= 0) {
        set_message(message, message_len, "pending Fighting Gong search must be resolved");
        return 31;
    }
    if (setup->pending_poke_pad_player >= 0) {
        set_message(message, message_len, "pending Poke Pad search must be resolved");
        return 32;
    }
    if (setup->pending_switch_player >= 0) {
        set_message(message, message_len, "pending Switch target must be resolved");
        return 33;
    }
    if (setup->pending_retreat_player >= 0) {
        set_message(message, message_len, "pending Retreat must be resolved");
        return 38;
    }
    if (setup->pending_aura_jab_player >= 0) {
        set_message(message, message_len, "pending Aura Jab attachments must be resolved");
        return 36;
    }
    memcpy(out_setup, setup, sizeof(PtcgBattleSetup));
    attacking_player = out_setup->current_player;
    defending_player = 1 - attacking_player;
    attacker = &out_setup->players[attacking_player];
    defender = &out_setup->players[defending_player];

    if (attacker->active_card_id == 0) {
        set_message(message, message_len, "attacking player has no Active Pokemon");
        return 17;
    }
    if (defender->active_card_id == 0) {
        set_message(message, message_len, "defending player has no Active Pokemon");
        return 18;
    }

    attacking_card = find_card_entry(attacker->active_card_id);
    defending_card = find_card_entry(defender->active_card_id);
    attack = find_attack_entry(attack_id);
    if (attacking_card == NULL || defending_card == NULL || attack == NULL) {
        set_message(message, message_len, "unknown attack or active card");
        return 1;
    }
    if (!card_has_attack(attacking_card, attack_id)) {
        set_message(message, message_len, "Active Pokemon does not have that attack");
        return 19;
    }
    if (!can_pay_attack_cost(attack, attacker->active_energy, attacker->active_energy_count)) {
        set_message(message, message_len, "not enough Energy to use that attack");
        return 20;
    }
    if (active_attack_is_disabled(attacker, attack_id, setup->turn)) {
        set_disabled_attack_message(message, message_len, attack);
        return 34;
    }

    damage = calculate_attack_damage(setup, attacker, attacking_card, defending_card, attack, attack_id);
    self_damage = attack_self_damage(attack_id);
    if (attack_locks_next_turn(attack_id)) {
        attacker->active_disabled_attack_id = attack_id;
        attacker->active_disabled_attack_turn = setup->turn + 2;
    }
    defender->active_damage += damage;
    attacker->active_damage += self_damage;
    out_setup->fighting_attack_bonus = 0;

    error = resolve_active_knockout(
        out_setup,
        defending_player,
        attacking_player,
        defending_player,
        message,
        message_len
    );
    if (error != 0) {
        return error;
    }
    if (out_setup->result < 0 && out_setup->pending_promotion_player < 0) {
        error = resolve_active_knockout(
            out_setup,
            attacking_player,
            defending_player,
            defending_player,
            message,
            message_len
        );
        if (error != 0) {
            return error;
        }
    }

    if (out_setup->result < 0 && out_setup->pending_promotion_player < 0) {
        maybe_start_aura_jab(out_setup, attack_id, attacking_player);
        if (out_setup->pending_aura_jab_player < 0) {
            error = advance_turn_after_attack_effect(out_setup, defending_player, message, message_len);
            if (error != 0) {
                return error;
            }
        }
    }

    set_message(message, message_len, "ok");
    return 0;
}
