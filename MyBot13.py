#!/usr/bin/env python3

# Import the Halite SDK, which will let you interact with the game.
import hlt
from hlt import constants
from hlt.positionals import *

import random
import logging
import math

game = hlt.Game()
ship_status = {}
ship_target = {}
ship_next_step_list = []
enemy_potential_step_list = []
f_log = []

last_build_turn = -999
target_getter_count = 0

STATE_EXPLORE = "explore"
STATE_RETURN = "return"
STATE_MINE = "mine"

MAX_NUM_SHIP = 50
BUILD_COOLDOWN = 0
MAX_TURN_BUILD_SHIP = 230
MIN_NUM_SHIP_WANTED = 3
STEP_FACTOR = 1

game.ready("MyPythonBot")


def estimate_step_required_to_mine(halite, cargo):
    max_step = max(math.floor(-0.00001326 * halite ** 2 + 0.0205 * halite - 1.15), 1)
    step = max_step - max_step * (cargo) / 1000
    return int(step)


def get_unsafe_full_moves(game_map, source, destination):
    source = game_map.normalize(source)
    destination = game_map.normalize(destination)

    distance = abs(destination - source)
    y_cardinality, x_cardinality = game_map._get_target_direction(source, destination)

    min_distance_x = 999
    min_distance_y = 999
    for x_offset in [game_map.width, 0, -game_map.height]:
        for y_offset in [game_map.height, 0, -game_map.height]:
            if abs(destination.x + x_offset - source.x) < min_distance_x:
                min_distance_x = abs(destination.x + x_offset - source.x)
            if abs(destination.y + y_offset - source.y) < min_distance_y:
                min_distance_y = abs(destination.y + y_offset - source.y)
    x_dir = x_cardinality if distance.x < (game_map.width / 2) else Direction.invert(x_cardinality)
    y_dir = y_cardinality if distance.y < (game_map.height / 2) else Direction.invert(y_cardinality)
    possible_moves = []
    possible_moves.extend([x_dir] * min_distance_x)
    possible_moves.extend([y_dir] * min_distance_y)
    random.shuffle(possible_moves)
    return possible_moves


def get_max_turn_build_ship(game_map, game):
    # extra_deduct = 0
    # if game_map.height <= 40:
    #     extra_deduct += -50
    return int(constants.MAX_TURNS * 0.5)


def get_current_explorable_area(game_map, max_explore_dist, shipyard_position):
    position_within_explore_range = []
    for x in range(game_map.width):
        for y in range(game_map.height):
            if game_map.calculate_distance(Position(x, y), shipyard_position) <= max_explore_dist:
                position_within_explore_range.append(Position(x, y))
    return position_within_explore_range


def search_best_expected_return_target(game_map, game_turn_number, shipyard_position, ship, avg_halite_ship_num_skip10):
    global f_log
    max_explore_dist = get_explore_dist(game_turn_number, game_map)

    position_within_explore_range = get_current_explorable_area(game_map, max_explore_dist, shipyard_position)
    logging.info("Ship{}.searchExpReturn. MaxExploDist={} len(ExploList)={}".format(ship.id, max_explore_dist, len(position_within_explore_range)))
    logging.info("avgHaSkip10={}".format(avg_halite_ship_num_skip10))

    target_results = []
    for target_pos in position_within_explore_range:
        is_ignore = False
        if ship.position == target_pos:
            log_str = "ExRe:SkipMyPos"
            is_ignore = True
        # if not is_exceed_mining_threshold(game_map, target_pos, game_map[target_pos].halite_amount, game_turn_number, avg_halite_ship_num_skip10, shipyard_position):
        #     log_str = "ExRe:NotExceedMineThreshold"
        #     is_ignore = True
        if not is_ignore:
            log_str = "ExRe:"
            total_step = game_map.calculate_distance(ship.position, target_pos) + estimate_step_required_to_mine(game_map[target_pos].halite_amount, ship.halite_amount) + game_map.calculate_distance(
                target_pos, shipyard_position)
            expected_gain_per_step = game_map[target_pos].halite_amount / (total_step ** STEP_FACTOR)
            target_results.append((target_pos, expected_gain_per_step, total_step))
            log_str = "G/S:{} St:{} Log:{}".format(expected_gain_per_step, total_step, log_str)
        if ship.id == 0:
            # logging.info(log_str)
            f_log = append_f_log(f_log, game_turn_number, target_pos.x, target_pos.y, log_str)

    # Find best cell
    target_results.sort(key=lambda tup: tup[1], reverse=True)
    for cell in target_results:
        pos = cell[0]
        if pos not in [value for key, value in ship_target.items()]:
            logging.info("search_best_expected_return_target() Ship{} pos:{}".format(ship.id, pos))
            return pos
    logging.info("No target. Ship:{} exploRange:{}".format(ship.id, [(pos.x, pos.y) for pos in position_within_explore_range]))
    logging.info("target_results: {}".format(target_results))
    logging.info("ship_target: {}".format(ship_target))
    raise Exception("search_best_expected_return_target() no target found")


def search_max_mine_list(game_map, game_turn_number, shipyard_position, enemy_shipyard_position) -> list:
    START_NO_COST_EFFECT_TURN_RATIO = 0.5
    DISTANCE_COST = 10 * max((int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO) - game_turn_number) / int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO), 0)
    ENEMY_DIST_REWARD = 5 * max((int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO) - game_turn_number) / int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO), 0)
    logging.info("search_max_mine_list() Turn {}. DISTANCE_COST: {}, ENEMY_DIST_REWARD: {}".format(game_turn_number, DISTANCE_COST, ENEMY_DIST_REWARD))
    max_explore_dist = get_explore_dist(game_turn_number, game_map)
    sorted_cells = []

    position_within_explore_range = get_current_explorable_area(game_map, max_explore_dist, shipyard_position)

    for pos in position_within_explore_range:
        cell_halite_amount = game_map[pos].halite_amount
        shipyard_dist_diff = game_map.calculate_distance(shipyard_position, pos)
        enemy_shipyard_dist_diff = game_map.calculate_distance(enemy_shipyard_position, pos)
        weighted_value = cell_halite_amount - shipyard_dist_diff * DISTANCE_COST + enemy_shipyard_dist_diff * ENEMY_DIST_REWARD
        sorted_cells.append((pos, weighted_value))
    sorted_cells.sort(key=lambda tup: tup[1], reverse=True)
    return sorted_cells


def get_explore_dist(game_turn_number, game_map):
    MIN_EXPLORE_DIST = 20
    MAX_EXPLORE_DIST = game_map.height
    return int(MIN_EXPLORE_DIST + (game_turn_number + 20) / constants.MAX_TURNS * (MAX_EXPLORE_DIST - MIN_EXPLORE_DIST))


def navigate(game_map, ship, destination, is_final_return, shipyard_position):
    # Check wanted direction
    global f_log

    # No fuel then stay -> stay
    if is_not_enough_fuel(ship, game_map):
        ship_next_step_list.append(ship.position)
        f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepMeNoFuelStop")
        return Direction.Still

    # Get safe directions
    safe_directions = []
    for direction in Direction.get_all_cardinals():
        pos = ship.position.directional_offset(direction)
        if pos not in ship_next_step_list:
            safe_directions.append(direction)

    # No safe directions
    if len(safe_directions) == 0:
        ship_next_step_list.append(ship.position)
        f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepNoSafeStay")
        return Direction.Still

    wander_direction = random.choice(safe_directions)
    wander_pos = ship.position.directional_offset(wander_direction)

    unsafe_moves = game_map.get_unsafe_moves(ship.position, destination)
    random.shuffle(unsafe_moves)

    # Game start cannot block
    if game.turn_number <= 5:
        for direction in unsafe_moves:
            target_pos = ship.position.directional_offset(direction)
            target_pos = game_map.normalize(target_pos)
            if target_pos in ship_next_step_list:
                ship_next_step_list.append(wander_pos)
                f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepMeTeamBlockEarlyForceWander dir:{} safe:{}".format(wander_direction, safe_directions))
                return wander_direction

    # Mining
    if ship.position == destination and ship.position not in ship_next_step_list:
        ship_next_step_list.append(ship.position)
        f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepMeMiningStop")
        return Direction.Still
    elif ship.position == destination and ship.position in ship_next_step_list:
        ship_next_step_list.append(wander_pos)
        f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepMeMiningBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
        return wander_direction

    # Completely clear -> move
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if target_pos not in ship_next_step_list + enemy_potential_step_list or (is_final_return and target_pos == shipyard_position):
            ship_next_step_list.append(target_pos)
            f_log = append_f_log(f_log, game.turn_number, target_pos.x, target_pos.y, "nextStepMeClearMove")
            return direction

    # Blocked by teammate and ship position clear -> stop
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if target_pos in ship_next_step_list and ship.position not in ship_next_step_list:
            ship_next_step_list.append(ship.position)
            f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepTeamBlockStop")
            return Direction.Still

    # Blocked by teammate and ship position not clear -> wander move
    # Blocked by enemy: wander/stay/move to target
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if target_pos in ship_next_step_list and ship.position in ship_next_step_list:
            ship_next_step_list.append(wander_pos)
            f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepTeamBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
            return wander_direction
        elif target_pos in enemy_potential_step_list and ship.position not in ship_next_step_list:
            random_num = random.uniform(0, 1)
            if random_num < 0.2:
                ship_next_step_list.append(target_pos)
                f_log = append_f_log(f_log, game.turn_number, target_pos.x, target_pos.y, "nextStepEnemyBlockMoveTarget")
                return direction
            elif random_num < 0.6:
                ship_next_step_list.append(ship.position)
                f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepEnemyBlockStop")
                return Direction.Still
            else:
                ship_next_step_list.append(wander_pos)
                f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepEnemyBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
                return wander_direction
        elif target_pos in enemy_potential_step_list and ship.position in ship_next_step_list:
            ship_next_step_list.append(wander_pos)
            f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepEnemyBlockCannotStayWander dir:{} safe:{}".format(wander_direction, safe_directions))
            return wander_direction

    # Not sure what case: wander
    ship_next_step_list.append(wander_pos)
    f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepLast dir:{} safe:{}".format(wander_direction, safe_directions))
    return wander_direction


def move_ship_to_position(command_queue, game_map, ship, target_position, is_final_return, shipyard_position):
    move = navigate(game_map, ship, target_position, is_final_return, shipyard_position)
    command_queue.append(ship.move(move))
    return command_queue


def log_action(action, ship, game_map):
    logging.info("log_action: {}, newStat: {}, newTarget: {}".format(action, ship_status[ship.id], ship_target[ship.id]))


def is_exceed_mining_threshold(game_map, mining_position, imagined_mining_pos_halite, game_turn_number, avg_halite_ship_num_skip10, shipyard_position):
    WAIT_FOR_MINING_THRESHOLD = 100
    CLOSE_TO_SHIPYARD_MAX_RATIO = 0.7
    CLOSE_TO_SHIPYARD_DIST = 10
    shipyard_ratio = min(CLOSE_TO_SHIPYARD_DIST, game_map.calculate_distance(shipyard_position, mining_position)) / CLOSE_TO_SHIPYARD_DIST * CLOSE_TO_SHIPYARD_MAX_RATIO
    shipyard_ratio = shipyard_ratio + (1 - shipyard_ratio) * (constants.MAX_TURNS - game_turn_number) / constants.MAX_TURNS

    if constants.MAX_TURNS > 420:
        ratio = 0.3
    else:
        ratio = 0.4

    if game_turn_number <= 200:
        threshold = WAIT_FOR_MINING_THRESHOLD * shipyard_ratio
    else:
        threshold = min(WAIT_FOR_MINING_THRESHOLD * shipyard_ratio, avg_halite_ship_num_skip10 * ratio * shipyard_ratio)
    if imagined_mining_pos_halite is not None:
        return imagined_mining_pos_halite > threshold
    else:
        return game_map[mining_position].halite_amount > threshold


def avoid_enemy_collision(enemy_potential_step_list, enemy_ship_positions, game):
    for enemy_ship_position in enemy_ship_positions:
        enemy_potential_step_list.append(enemy_ship_position)
        enemy_potential_step_list.extend(enemy_ship_position.get_surrounding_cardinals())

    global f_log
    for pos in enemy_potential_step_list:
        f_log = append_f_log(f_log, game.turn_number, pos.x, pos.y, "nextStepEnemy")
    return enemy_potential_step_list


def append_f_log(f_log: list, t, x, y, msg) -> list:
    f_log.append({'t': t - 1, 'x': x, 'y': y, 'msg': msg})
    return f_log


def is_not_enough_fuel(ship, game_map):
    return ship.halite_amount < game_map[ship.position].halite_amount / 10


def is_enemy_blocking_shipyard(me, enemy_ship_positions):
    return me.halite_amount >= constants.SHIP_COST and me.shipyard.position in enemy_ship_positions


def should_build_ship(me, game, game_map):
    return len(me.get_ships()) < MAX_NUM_SHIP and me.halite_amount >= constants.SHIP_COST and me.shipyard.position not in ship_next_step_list and game.turn_number <= get_max_turn_build_ship(game_map,
                                                                                                                                                                                              game)


def find_enemy_ship_positions(game):
    enemy_ship_positions = []
    for player_id in range(len(game.players)):
        if game.my_id != player_id:
            enemy_ships = game.players[player_id].get_ships()
            for enemy_ship in enemy_ships:
                enemy_ship_positions.append(enemy_ship.position)
    return enemy_ship_positions


try:
    while True:
        game.update_frame()
        me = game.me

        # get enemy
        for player_id in range(len(game.players)):
            if game.my_id != player_id:
                enemy_id = player_id  # Find randomly one oppoent
                break
        logging.info("Targeted Enemy: {}".format(enemy_id))
        enemy = game.players[enemy_id]

        # total_ship_num
        total_ship_num = 0
        for player_id in range(len(game.players)):
            total_ship_num += len(game.players[player_id].get_ships())

        game_map = game.game_map

        command_queue = []
        ship_next_step_list = []
        enemy_potential_step_list = []
        enemy_ship_positions = find_enemy_ship_positions(game)
        enemy_potential_step_list = avoid_enemy_collision(enemy_potential_step_list, enemy_ship_positions, game)

        # cell priority
        sorted_cells = search_max_mine_list(game_map, game.turn_number, me.shipyard.position, enemy.shipyard.position)

        # halite_list = []
        # for cell in sorted_cells:
        #     halite_value = cell[1]
        #     halite_list.append(halite_value)
        # avg_halite_all = sum(halite_list) / (total_ship_num + 0.001)
        # avg_halite_ship_num = sum(halite_list[:total_ship_num]) / (total_ship_num + 0.001)
        # avg_halite_ship_num_skip10 = sum(halite_list[10:total_ship_num]) / (total_ship_num + 0.001)
        avg_halite_ship_num_skip10 = sum([c[1] for c in sorted_cells[10:10 + total_ship_num]]) / (total_ship_num + 0.001)
        # logging.info("total_ship_num : {}, avg_halite(all, ship#, ship#skip10): {}, {}, {}, sorted_cells: {}".format(total_ship_num, avg_halite_all, avg_halite_ship_num, avg_halite_ship_num_skip10,
        logging.info("total_ship_num : {}, avg_halite(ship#skip10): {}, sorted_cells: {}".format(
            total_ship_num, avg_halite_ship_num_skip10, [(c[0].x, c[0].y, round(c[1], 2)) for c in sorted_cells[:100]]))

        # init ship
        for ship in me.get_ships():
            if ship.id not in ship_status:
                ship_status[ship.id] = STATE_EXPLORE
            if ship.id not in ship_target:
                ship_target[ship.id] = search_best_expected_return_target(game_map, game.turn_number, me.shipyard.position, ship, avg_halite_ship_num_skip10)

        # Priority ships
        ships_will_be_stayed = []
        for ship in me.get_ships():
            logging.info("**SHIP** id:{} halite:{} pos:{},{} pos_halite:{} status={}".format(
                ship.id, ship.halite_amount, ship.position.x, ship.position.y, game_map[ship.position].halite_amount, ship_status[ship.id]))
            # No energy
            if is_not_enough_fuel(ship, game_map):
                ships_will_be_stayed.append(ship)
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)
                log_action("NoEnergy->Stay", ship, game_map)
            # Final return
            elif constants.MAX_TURNS - game.turn_number <= game_map.height * 0.75:
                ships_will_be_stayed.append(ship)
                command_queue = move_ship_to_position(command_queue, game_map, ship, me.shipyard.position, True, me.shipyard.position)
                log_action("FinalReturn->{}".format(me.shipyard.position), ship, game_map)
            # Mine
            elif is_exceed_mining_threshold(game_map, ship.position, None, game.turn_number, avg_halite_ship_num_skip10, me.shipyard.position) and not ship.is_full and game.turn_number >= 5:
                ships_will_be_stayed.append(ship)
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)
                log_action("Mining->Stay", ship, game_map)

        # Normal ships
        for ship in [ship for ship in me.get_ships() if ship not in ships_will_be_stayed]:
            logging.info("**SHIP** id:{} halite:{} pos:{},{} pos_halite:{} status={}".format(
                ship.id, ship.halite_amount, ship.position.x, ship.position.y, game_map[ship.position].halite_amount, ship_status[ship.id]))
            # Explore/return
            if ship_status[ship.id] == STATE_RETURN:
                if ship.position == me.shipyard.position:
                    ship_status[ship.id] = STATE_EXPLORE
                    del ship_target[ship.id]
                    ship_target[ship.id] = search_best_expected_return_target(game_map, game.turn_number, me.shipyard.position, ship, avg_halite_ship_num_skip10)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                    log_action("StartExplore->{}".format(ship_target[ship.id]), ship, game_map)
                    continue
                else:
                    command_queue = move_ship_to_position(command_queue, game_map, ship, me.shipyard.position, False, None)
                    log_action("Returning->{}".format(me.shipyard.position), ship, game_map)
                    continue
            elif ship_status[ship.id] == STATE_EXPLORE:
                if ship.halite_amount >= 250 + (constants.MAX_TURNS - game.turn_number) / constants.MAX_TURNS * 200:
                    ship_status[ship.id] = STATE_RETURN
                    command_queue = move_ship_to_position(command_queue, game_map, ship, me.shipyard.position, False, None)
                    log_action("StartReturn->{}".format(me.shipyard.position), ship, game_map)
                    continue
                elif ship.position == ship_target[ship.id]:
                    ship_target[ship.id] = search_best_expected_return_target(game_map, game.turn_number, me.shipyard.position, ship, avg_halite_ship_num_skip10)
                    log_action("ExploreChangeTarget->{}".format(ship_target[ship.id]), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                else:
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                    log_action("Exploring->{}".format(ship_target[ship.id]), ship, game_map)
                    continue
            else:
                raise Exception("Unknown status {}".format(ship_status[ship.id]))

        if should_build_ship(me, game, game_map) or is_enemy_blocking_shipyard(me, enemy_ship_positions):
            command_queue.append(game.me.shipyard.spawn())
            last_build_turn = game.turn_number

        logging.info("command_queue = {}".format(command_queue))

        if game.turn_number == constants.MAX_TURNS:
            import json

            with open("replays/f_log_p{}.log".format(game.my_id), "w") as f:
                f.write(json.dumps(f_log, indent=1))

        game.end_turn(command_queue)
except Exception as e:
    import traceback, sys

    exc_type, exc_value, exc_traceback = sys.exc_info()
    logging.info(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
