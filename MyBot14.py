#!/usr/bin/env python3

# Import the Halite SDK, which will let you interact with the game.
import hlt
from hlt import constants
from hlt.positionals import *

import random
import logging
import math

# import cProfile

game = hlt.Game()
ship_status = {}
ship_target = {}
ship_next_step_list = {}
enemy_potential_step_list = []
dropoff_dict = {}
f_log = []

last_build_turn = -999
last_dropoff_turn = -999
saved_halite_for_dropoff = 0
target_getter_count = 0

STATE_EXPLORE = "ex"
STATE_RETURN = "re"
STATE_MINE = "mi"
STATE_DROPOFF = "dr"

MAX_NUM_SHIP = 50
MAX_NUM_DROPOFF = 3
BUILD_COOLDOWN = 0
MAX_TURN_BUILD_SHIP = 230
MIN_NUM_SHIP_WANTED = 3
MIN_NEIGHHOUR_VALUE = 10000
STEP_FACTOR = 1
MIN_DROPOFF_TURN = 130
DROPOFF_TURN_FINAL_RETURN_GAP = 30

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
    return int(constants.MAX_TURNS * 0.5)


def get_area_by_archor_and_dist(game_map, max_dist, archor_list):
    position_within_explore_range = []
    for x in range(game_map.width):
        for y in range(game_map.height):
            if (x, y) in archor_list:
                continue
            for key, value in archor_list.items():
                archor_pos = Position(key[0], key[1])
                if game_map.calculate_distance(Position(x, y), archor_pos) <= max_dist:
                    position_within_explore_range.append(Position(x, y))
                    break
    return position_within_explore_range


def search_best_expected_return_target(game_map, game_turn_number, ship, avg_halite_ship_num_skip10, sorted_explorable_cells):
    global f_log
    logging.info("Ship{}.searchExpReturn. len(ExploList)={}".format(ship.id, len(sorted_explorable_cells)))
    logging.info("avgHaSkip10={}".format(avg_halite_ship_num_skip10))

    target_results = []
    for target_pos in [cell[0] for cell in sorted_explorable_cells[:int(len(sorted_explorable_cells) / 2)]]:
        is_ignore = False
        if ship.position == target_pos:
            log_str = "ExRe:SkipMyPos"
            is_ignore = True
        if not is_ignore:
            log_str = "ExRe:"
            total_step = game_map.calculate_distance(ship.position, target_pos) + estimate_step_required_to_mine(game_map[target_pos].halite_amount, ship.halite_amount) + game_map.calculate_distance(
                target_pos, find_closest_dropoff(game_map, ship))
            expected_gain_per_step = game_map[target_pos].halite_amount / (total_step ** STEP_FACTOR)
            target_results.append((target_pos, expected_gain_per_step, total_step))
            log_str = "G/S:{} St:{} Log:{}".format(expected_gain_per_step, total_step, log_str)
        # if ship.id == 0:
        # f_log = append_f_log(f_log, game_turn_number, target_pos.x, target_pos.y, log_str)

    # Find best cell
    target_results.sort(key=lambda tup: tup[1], reverse=True)
    for cell in target_results:
        pos = cell[0]
        if pos not in [value for key, value in ship_target.items()]:
            logging.info("search_best_expected_return_target() Ship{} pos:{}".format(ship.id, pos))
            return pos
    logging.info("No target. Ship:{} exploRange:{}".format(ship.id, [(pos.x, pos.y) for pos in sorted_explorable_cells]))
    logging.info("target_results: {}".format(target_results))
    logging.info("ship_target: {}".format(ship_target))
    raise Exception("search_best_expected_return_target() no target found")


def search_best_dropoff_point(game_map, sorted_cells, game_turn_number):
    NEIGHBORHOOD_DIST = 6
    max_explore_dist = get_explore_dist(game_turn_number, game_map)
    OUTER_DIST = 5
    min_dist_between_new_dropoff_curr_dropoff = 20 - OUTER_DIST

    possible_dropoff_positions = []
    for cell in sorted_cells:
        pos = cell[0]

        is_too_close = False
        for key, value in dropoff_dict.items():
            dropoff_pos = Position(key[0], key[1])
            if game_map.calculate_distance(pos, dropoff_pos) <= min_dist_between_new_dropoff_curr_dropoff:
                is_too_close = True
                break

        if is_too_close:
            continue

        neighbour_value = 0
        for neighbour_pos in get_area_by_archor_and_dist(game_map, NEIGHBORHOOD_DIST, {(pos.x, pos.y): (None, None)}):
            neighbour_value += game_map[neighbour_pos].halite_amount

        if neighbour_value > MIN_NEIGHHOUR_VALUE:
            possible_dropoff_positions.append((pos, neighbour_value))
    possible_dropoff_positions.sort(key=lambda tup: tup[1], reverse=True)
    return possible_dropoff_positions


def search_max_mine_list(game_map, game_turn_number, shipyard_position, enemy_shipyard_position) -> list:
    START_NO_COST_EFFECT_TURN_RATIO = 0.5
    DISTANCE_COST = 10 * max((int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO) - game_turn_number) / int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO), 0)
    ENEMY_DIST_REWARD = 5 * max((int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO) - game_turn_number) / int(constants.MAX_TURNS * START_NO_COST_EFFECT_TURN_RATIO), 0)
    logging.info("search_max_mine_list() Turn {}. DISTANCE_COST: {}, ENEMY_DIST_REWARD: {}".format(game_turn_number, DISTANCE_COST, ENEMY_DIST_REWARD))
    max_explore_dist = get_explore_dist(game_turn_number, game_map)
    sorted_cells = []

    position_within_explore_range = get_area_by_archor_and_dist(game_map, max_explore_dist, dropoff_dict)

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
        ship_next_step_list[(ship.position.x, ship.position.y)] = ship.id
        logging.info("  actual: nextStepMeNoFuelStop")
        f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepMeNoFuelStop")
        return Direction.Still

    # Get safe directions
    safe_directions = []
    for direction in Direction.get_all_cardinals():
        pos = ship.position.directional_offset(direction)
        pos = game_map.normalize(pos)
        if (pos.x, pos.y) not in ship_next_step_list:
            safe_directions.append(direction)

    # No safe directions
    if len(safe_directions) == 0:
        ship_next_step_list[(ship.position.x, ship.position.y)] = ship.id
        logging.info("  actual: nextStepNoSafeStay")
        f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepNoSafeStay")
        return Direction.Still

    wander_direction = random.choice(safe_directions)
    wander_pos = ship.position.directional_offset(wander_direction)
    wander_pos = game_map.normalize(wander_pos)

    unsafe_moves = game_map.get_unsafe_moves(ship.position, destination)
    random.shuffle(unsafe_moves)

    # Game start cannot block
    if game.turn_number <= 5:
        for direction in unsafe_moves:
            target_pos = ship.position.directional_offset(direction)
            target_pos = game_map.normalize(target_pos)
            if (target_pos.x, target_pos.y) in ship_next_step_list:
                ship_next_step_list[(wander_pos.x, wander_pos.y)] = ship.id
                logging.info("  actual: nextStepMeTeamBlockEarlyForceWander dir:{} safe:{}".format(wander_direction, safe_directions))
                f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepMeTeamBlockEarlyForceWander dir:{} safe:{}".format(wander_direction, safe_directions))
                return wander_direction

    # Mining
    if ship.position == destination and (ship.position.x, ship.position.y) not in ship_next_step_list:
        ship_next_step_list[(ship.position.x, ship.position.y)] = ship.id
        logging.info("  actual: nextStepMeMiningStop")
        f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepMeMiningStop")
        return Direction.Still
    elif ship.position == destination and (ship.position.x, ship.position.y) in ship_next_step_list:
        ship_next_step_list[(wander_pos.x, wander_pos.y)] = ship.id
        logging.info("  actual: nextStepMeMiningBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
        f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepMeMiningBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
        return wander_direction

    # Completely clear -> move
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if ((target_pos.x, target_pos.y) not in ship_next_step_list and (target_pos.x, target_pos.y) not in enemy_potential_step_list) or (
                is_final_return and target_pos == find_closest_dropoff(game_map, ship)
        ):
            ship_next_step_list[(target_pos.x, target_pos.y)] = ship.id
            logging.info("  actual: nextStepMeClearMove t:{} s:{}({},{}) t:({},{}) dir:{}({},{})[{}] us_mo:{} ".format(
                game.turn_number, ship.id, ship.position.x, ship.position.y,
                target_pos.x, target_pos.y,
                direction, direction[0], direction[1], Direction.convert(direction), unsafe_moves
            ))
            f_log = append_f_log(f_log, game.turn_number, target_pos.x, target_pos.y, "nextStepMeClearMove")
            return direction

    # Blocked by teammate and ship position clear -> stop
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if (target_pos.x, target_pos.y) in ship_next_step_list and (ship.position.x, ship.position.y) not in ship_next_step_list:
            ship_next_step_list[(ship.position.x, ship.position.y)] = ship.id
            logging.info("  actual: nextStepTeamBlockStop")
            f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepTeamBlockStop")
            return Direction.Still

    # Blocked by teammate and ship position not clear -> wander move
    # Blocked by enemy: wander/stay/move to target
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if (target_pos.x, target_pos.y) in ship_next_step_list and (ship.position.x, ship.position.y) in ship_next_step_list:
            ship_next_step_list[(wander_pos.x, wander_pos.y)] = ship.id
            logging.info("  actual: nextStepTeamBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
            f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepTeamBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
            return wander_direction
        elif (target_pos.x, target_pos.y) in enemy_potential_step_list and (ship.position.x, ship.position.y) not in ship_next_step_list:
            random_num = random.uniform(0, 1)
            if random_num < 0.2:
                ship_next_step_list[(target_pos.x, target_pos.y)] = ship.id
                logging.info("  actual: nextStepEnemyBlockMoveTarget dir:{}".format(direction))
                f_log = append_f_log(f_log, game.turn_number, target_pos.x, target_pos.y, "nextStepEnemyBlockMoveTarget")
                return direction
            elif random_num < 0.6:
                ship_next_step_list[(ship.position.x, ship.position.y)] = ship.id
                logging.info("  actual: nextStepEnemyBlockStop")
                f_log = append_f_log(f_log, game.turn_number, ship.position.x, ship.position.y, "nextStepEnemyBlockStop")
                return Direction.Still
            else:
                ship_next_step_list[(wander_pos.x, wander_pos.y)] = ship.id
                logging.info("  actual: nextStepEnemyBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
                f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepEnemyBlockWander dir:{} safe:{}".format(wander_direction, safe_directions))
                return wander_direction
        elif (target_pos.x, target_pos.y) in enemy_potential_step_list and (ship.position.x, ship.position.y) in ship_next_step_list:
            ship_next_step_list[(wander_pos.x, wander_pos.y)] = ship.id
            logging.info("  actual: nextStepEnemyBlockCannotStayWander dir:{} safe:{}".format(wander_direction, safe_directions))
            f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepEnemyBlockCannotStayWander dir:{} safe:{}".format(wander_direction, safe_directions))
            return wander_direction

    # Not sure what case: wander
    ship_next_step_list[(wander_pos.x, wander_pos.y)] = ship.id
    logging.info("  actual: nextStepLast dir:{} safe:{}".format(wander_direction, safe_directions))
    f_log = append_f_log(f_log, game.turn_number, wander_pos.x, wander_pos.y, "nextStepLast dir:{} safe:{}".format(wander_direction, safe_directions))
    return wander_direction


def move_ship_to_position(command_queue, game_map, ship, target_position, is_final_return, shipyard_position):
    move = navigate(game_map, ship, target_position, is_final_return, shipyard_position)
    command_queue.append(ship.move(move))
    return command_queue


def log_action(action, ship, game_map):
    logging.info("**SHIP** id:{} halite:{} pos:{},{} pos_halite:{} status={}".format(
        ship.id, ship.halite_amount, ship.position.x, ship.position.y, game_map[ship.position].halite_amount, ship_status[ship.id]))
    logging.info("  Action: {}, curStat: {}, curTarget: {}".format(action, ship_status[ship.id], ship_target[ship.id]))


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


def get_mining_threshold(game_map, mining_position, game_turn_number, avg_halite_ship_num_skip10, shipyard_position):
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
    return threshold


def should_mine(ship, game_map, mining_position, game_turn_number, shipyard_position):
    return game_map[mining_position].halite_amount > get_mining_threshold(
        game_map, mining_position, game_turn_number, avg_halite_ship_num_skip10, shipyard_position
    ) and ship_status[ship.id] != STATE_DROPOFF and not ship.is_full and game.turn_number >= 5


def avoid_enemy_collision(enemy_potential_step_list, enemy_ship_positions, game):
    for enemy_ship_position in enemy_ship_positions:
        enemy_potential_step_list[(enemy_ship_position.x, enemy_ship_position.y)] = 1
        for pos in enemy_ship_position.get_surrounding_cardinals():
            enemy_potential_step_list[(pos.x, pos.y)] = 1

    global f_log
    for pos in enemy_potential_step_list:
        f_log = append_f_log(f_log, game.turn_number, pos[0], pos[1], "nextStepEnemy")
    return enemy_potential_step_list


def find_closest_dropoff(game_map, ship):
    min_dist = 999
    min_dist_dropoff = None
    for key, value in dropoff_dict.items():
        dropoff_pos = Position(key[0], key[1])
        dist = game_map.calculate_distance(dropoff_pos, ship.position)
        if dist < min_dist:
            min_dist = dist
            min_dist_dropoff = dropoff_pos
    return min_dist_dropoff


def append_f_log(f_log: list, t, x, y, msg) -> list:
    f_log.append({'t': t - 1, 'x': x, 'y': y, 'msg': msg})
    return f_log


def is_not_enough_fuel(ship, game_map):
    return ship.halite_amount < game_map[ship.position].halite_amount / 10


def is_enemy_blocking_shipyard(me, enemy_ship_positions):
    return me.halite_amount >= constants.SHIP_COST and me.shipyard.position in enemy_ship_positions


def should_build_ship(me, game, game_map):
    is_under_ship_amount_cap = len(me.get_ships()) < MAX_NUM_SHIP
    have_halite = me.halite_amount >= constants.SHIP_COST
    have_halite_extra_for_dropoff = me.halite_amount >= saved_halite_for_dropoff
    is_friendly_not_in_shipyard = (me.shipyard.position.x, me.shipyard.position.y) not in ship_next_step_list
    is_under_turn_cap = game.turn_number <= get_max_turn_build_ship(game_map, game)
    return is_under_ship_amount_cap and have_halite and have_halite_extra_for_dropoff and is_friendly_not_in_shipyard and is_under_turn_cap


def can_build_dropoff(game, me):
    return len(dropoff_dict) - 1 < MAX_NUM_DROPOFF and MIN_DROPOFF_TURN <= game.turn_number <= get_final_return_turn(
        game) - DROPOFF_TURN_FINAL_RETURN_GAP and game.turn_number % 5 == 1 and me.halite_amount > constants.DROPOFF_COST and game.turn_number - last_dropoff_turn >= 20


def get_final_return_turn(game):
    return constants.MAX_TURNS - game_map.height * 0.75


def find_enemy_ship_positions(game):
    enemy_ship_positions = []
    for player_id in range(len(game.players)):
        if game.my_id != player_id:
            enemy_ships = game.players[player_id].get_ships()
            for enemy_ship in enemy_ships:
                enemy_ship_positions.append(enemy_ship.position)
    return enemy_ship_positions


def sort_ship_by_surrounding_ship(game_map, ships, all_ship_position):
    ship_neighbour_list = []
    for ship in ships:
        count = 0
        for direction in Direction.get_all_cardinals():
            neighbour_pos = ship.position.directional_offset(direction)
            neighbour_pos = game_map.normalize(neighbour_pos)
            if neighbour_pos in all_ship_position:
                count += 1
        ship_neighbour_list.append((ship, count))
    ship_neighbour_list.sort(key=lambda tup: tup[1], reverse=True)
    logging.info("ship_neighbour_list:{}".format([(tup[0].id, tup[1]) for tup in ship_neighbour_list]))
    return [tup[0] for tup in ship_neighbour_list]


def find_closest_ship(me, game_map, target_pos):
    closest_ship = None
    closest_dist = 999
    for ship in me.get_ships():
        if ship_status[ship.id] == STATE_RETURN:
            continue
        dist = game_map.calculate_distance(ship.position, target_pos)
        if dist < closest_dist:
            closest_ship = ship
            closest_dist = dist
    return closest_ship, closest_dist


# get enemy
for player_id in range(len(game.players)):
    if game.my_id != player_id:
        enemy_id = player_id  # Find randomly one oppoent
        break
logging.info("Targeted Enemy: {}".format(enemy_id))
enemy = game.players[enemy_id]

import cProfile, pstats, io

# pr = cProfile.Profile()
# pr.enable()

try:
    while True:
        game.update_frame()
        me = game.me

        # total_ship_num
        total_ship_num = 0
        for player_id in range(len(game.players)):
            total_ship_num += len(game.players[player_id].get_ships())

        game_map = game.game_map

        command_queue = []
        ship_next_step_list = {}
        enemy_potential_step_list = {}
        enemy_ship_positions = find_enemy_ship_positions(game)
        all_ship_position = enemy_ship_positions + [ship.position for ship in me.get_ships()]
        enemy_potential_step_list = avoid_enemy_collision(enemy_potential_step_list, enemy_ship_positions, game)

        # cell priority
        sorted_explorable_cells = search_max_mine_list(game_map, game.turn_number, me.shipyard.position, enemy.shipyard.position)

        if game.turn_number == 1:
            dropoff_dict[(me.shipyard.position.x, me.shipyard.position.y)] = (None, True)  # ship_id, is_built

        avg_halite_ship_num_skip10 = sum([c[1] for c in sorted_explorable_cells[10:10 + total_ship_num]]) / (total_ship_num + 0.001)
        logging.info("total_ship_num : {}, avg_halite(ship#skip10): {}, dropoff_list: {}".format(total_ship_num, round(avg_halite_ship_num_skip10, 2), dropoff_dict))
        logging.info("sorted_cells: {}".format([(c[0].x, c[0].y, round(c[1], 2)) for c in sorted_explorable_cells[:100]]))

        # init ship
        for ship in me.get_ships():
            if ship.id not in ship_status:
                ship_status[ship.id] = STATE_EXPLORE
            if ship.id not in ship_target:
                ship_target[ship.id] = search_best_expected_return_target(game_map, game.turn_number, ship, avg_halite_ship_num_skip10, sorted_explorable_cells)
        commanded_ships = []

        # Check if dropoff ship died
        my_ship_ids = [ship.id for ship in me.get_ships()]
        for key, value in dropoff_dict.items():
            dropoff_pos = Position(key[0], key[1])
            assigned_ship_id = value[0]
            is_built = value[1]
            if not is_built and assigned_ship_id not in my_ship_ids:
                closest_ship, closest_dist = find_closest_ship(me, game_map, dropoff_pos)
                ship_target[closest_ship.id] = dropoff_pos
                ship_status[closest_ship.id] = STATE_DROPOFF
                dropoff_dict[(dropoff_pos.x, dropoff_pos.y)] = (closest_ship.id, False)

        # Create dropoff
        EVAL_NUM_DROPOFF = 10
        if can_build_dropoff(game, me):
            best_dropff_points = search_best_dropoff_point(game_map, sorted_explorable_cells[:EVAL_NUM_DROPOFF], game.turn_number)
            logging.info("t={} possibleDropoffs:{}".format(game.turn_number, best_dropff_points))
            if len(best_dropff_points) > 0:
                # Evaluate if better than current dropoff points
                best_dropoff_point_pos = best_dropff_points[0][0]
                best_dropoff_point_value = best_dropff_points[0][1]
                original_dropoff_points = [potential_dropoff_pos for potential_dropoff_pos in best_dropff_points if (potential_dropoff_pos[0].x, potential_dropoff_pos[0].y) in dropoff_dict]
                should_build = True
                for original_dropoff_point in original_dropoff_points:
                    original_dropoff_point_pos = original_dropoff_point[0]
                    original_dropoff_point_value = original_dropoff_point[1]
                    logging.info("evalDropoff: orig:({},{})={} new:({},{})={}".format(
                        original_dropoff_point_pos.x, original_dropoff_point_pos.y, original_dropoff_point_value,
                        best_dropoff_point_pos.x, best_dropoff_point_pos.y, best_dropoff_point_value
                    ))
                    if original_dropoff_point_value * 3 < best_dropoff_point_value:
                        should_build = False
                if should_build:
                    closest_ship, closest_dist = find_closest_ship(me, game_map, best_dropoff_point_pos)
                    ship_target[closest_ship.id] = best_dropoff_point_pos
                    ship_status[closest_ship.id] = STATE_DROPOFF
                    last_dropoff_turn = game.turn_number
                    saved_halite_for_dropoff += constants.DROPOFF_COST
                    dropoff_dict[(best_dropoff_point_pos.x, best_dropoff_point_pos.y)] = (closest_ship.id, False)
                    logging.info("t={} assignedShip:{} d={} bestdropoff:{}".format(game.turn_number, closest_ship, closest_dist, best_dropff_points))

        # Priority ships
        for ship in [ship for ship in me.get_ships() if ship not in commanded_ships]:
            closest_dropoff_pos = find_closest_dropoff(game_map, ship)
            # No energy
            if is_not_enough_fuel(ship, game_map):
                commanded_ships.append(ship)
                log_action("NoEnergy->Stay", ship, game_map)
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)
            # Final return
            elif game.turn_number >= get_final_return_turn(game):
                commanded_ships.append(ship)
                log_action("FinalReturn->{}".format(closest_dropoff_pos), ship, game_map)
                command_queue = move_ship_to_position(command_queue, game_map, ship, closest_dropoff_pos, True, me.shipyard.position)

        # Mine
        for ship in [ship for ship in me.get_ships() if ship not in commanded_ships]:
            if should_mine(ship, game_map, ship.position, game.turn_number, me.shipyard.position):
                commanded_ships.append(ship)
                log_action("Mining->Stay", ship, game_map)
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)

        # Normal ships
        remaining_ships = [ship for ship in me.get_ships() if ship not in commanded_ships]
        remaining_ships = sort_ship_by_surrounding_ship(game_map, remaining_ships, all_ship_position)
        for ship in remaining_ships:
            closest_dropoff_pos = find_closest_dropoff(game_map, ship)
            # Explore/return
            if ship_status[ship.id] == STATE_DROPOFF:
                if ship.position == ship_target[ship.id]:
                    if me.halite_amount > constants.DROPOFF_COST:
                        log_action("MakeDropoffHaveHalite->{}".format(ship_target[ship.id]), ship, game_map)
                        command_queue.append(ship.make_dropoff())
                        saved_halite_for_dropoff -= constants.DROPOFF_COST
                        dropoff_dict[(ship.position.x, ship.position.y)] = (None, True)
                        continue
                    else:
                        log_action("MakeDropoffNoHalite->{}".format(ship_target[ship.id]), ship, game_map)
                        command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)
                        continue
                else:
                    log_action("GoingDropoff->{}".format(ship_target[ship.id]), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                    continue
            elif ship_status[ship.id] == STATE_RETURN:
                if ship.position == closest_dropoff_pos:
                    ship_status[ship.id] = STATE_EXPLORE
                    ship_target[ship.id] = search_best_expected_return_target(game_map, game.turn_number, ship, avg_halite_ship_num_skip10, sorted_explorable_cells)
                    log_action("StartExplore->{}".format(ship_target[ship.id]), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                    continue
                else:
                    log_action("Returning->{}".format(closest_dropoff_pos), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, closest_dropoff_pos, False, None)
                    continue
            elif ship_status[ship.id] == STATE_EXPLORE:
                if ship.halite_amount >= 250 + (constants.MAX_TURNS - game.turn_number) / constants.MAX_TURNS * 200:
                    ship_status[ship.id] = STATE_RETURN
                    log_action("StartReturn->{}".format(closest_dropoff_pos), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, closest_dropoff_pos, False, None)
                    continue
                elif ship.position == ship_target[ship.id]:
                    ship_target[ship.id] = search_best_expected_return_target(game_map, game.turn_number, ship, avg_halite_ship_num_skip10, sorted_explorable_cells)
                    log_action("ExploreChangeTarget->{}".format(ship_target[ship.id]), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                    continue
                else:
                    log_action("Exploring->{}".format(ship_target[ship.id]), ship, game_map)
                    command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                    continue
            else:
                raise Exception("Unknown status {}".format(ship_status[ship.id]))

        if should_build_ship(me, game, game_map) or is_enemy_blocking_shipyard(me, enemy_ship_positions):
            command_queue.append(game.me.shipyard.spawn())
            last_build_turn = game.turn_number

        logging.info("ship_next_step_list={}".format(ship_next_step_list))
        logging.info("command_queue = {}".format(command_queue))

        if game.turn_number == constants.MAX_TURNS:
            import json

            with open("replays/f_log_p{}.log".format(game.my_id), "w") as f:
                f.write(json.dumps(f_log, indent=1))

            # pr.disable()
            # s = io.StringIO()
            # sortby = 'cumulative'
            # ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            # ps.print_stats()
            #
            # with open("replays/profile.log", "w") as f:
            #     f.write(s.getvalue())

        game.end_turn(command_queue)
except Exception as e:
    import traceback, sys

    exc_type, exc_value, exc_traceback = sys.exc_info()
    logging.info(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
