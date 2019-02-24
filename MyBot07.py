#!/usr/bin/env python3

# Import the Halite SDK, which will let you interact with the game.
import hlt
from hlt import constants
from hlt.positionals import *

import random
import logging

game = hlt.Game()
ship_status = {}
ship_target = {}
ship_next_step_list = []

last_build_turn = -999
target_getter_count = 0

STATE_EXPLORE = "explore"
STATE_RETURN = "return"
STATE_MINE = "mine"

MAX_NUM_SHIP = 40
BUILD_COOLDOWN = 0
EXPLORE_DIST = 20
MAX_TURN_BUILD_SHIP = 230
MIN_NUM_SHIP_WANTED = 3

game.ready("MyPythonBot")

def get_max_turn_build_ship(game_map):
    height = game_map.height

def search_max_mine(game_map, game_turn_number, shipyard_position, x_multiplier, y_multiplier) -> Position:
    best_pos = shipyard_position
    best_pos_halite = 0
    max_explore_dist = get_explore_dist(game_turn_number, game_map)
    for x_offset in range(max_explore_dist):
        x = (shipyard_position.x + x_offset * x_multiplier) % game_map.width
        for y_offset in range(max_explore_dist):
            y = (shipyard_position.y + y_offset * y_multiplier) % game_map.height
            # logging.info("max_explore_dist, x_offset, y_offset, x, y: {}, {}, {}, {}, {}".format(max_explore_dist, x_offset, y_offset, x, y))
            # logging.info(game_map[Position(x, y)])
            cell_halite_amount = game_map[Position(x, y)].halite_amount
            # logging.info("max_explore_dist, x, y, cell_halite_amount: {}, {}, {}, {}".format(max_explore_dist, x, y, cell_halite_amount))
            if cell_halite_amount > best_pos_halite:
                best_pos = Position(x, y)
                best_pos_halite = cell_halite_amount
                # logging.info("new best: {}, {}".format(best_pos, best_pos_halite))
    return best_pos


def search_max_mine_list(game_map, game_turn_number, shipyard_position, enemy_shipyard_position) -> list:
    DISTANCE_COST = 10
    ENEMY_DIST_COST = 5
    logging.info("search_max_mine_list() Turn {}".format(game_turn_number))
    max_explore_dist = get_explore_dist(game_turn_number, game_map)
    sorted_cells = []
    for x_offset in range(-max_explore_dist, max_explore_dist + 1):
        x = (shipyard_position.x + x_offset) % game_map.width
        for y_offset in range(-max_explore_dist, max_explore_dist + 1):
            y = (shipyard_position.y + y_offset) % game_map.height
            # logging.info("max_explore_dist, x_offset, y_offset, x, y: {}, {}, {}, {}, {}".format(max_explore_dist, x_offset, y_offset, x, y))
            # logging.info(game_map[Position(x, y)])
            cell_halite_amount = game_map[Position(x, y)].halite_amount
            weighted_value = cell_halite_amount - game_map.calculate_distance(shipyard_position, Position(x, y)) * DISTANCE_COST + game_map.calculate_distance(enemy_shipyard_position, Position(x, y)) * ENEMY_DIST_COST

            sorted_cells.append((Position(x, y), weighted_value))
            # logging.info("max_explore_dist, x, y, cell_halite_amount: {}, {}, {}, {}".format(max_explore_dist, x, y, cell_halite_amount))
            # if cell_halite_amount > best_pos_halite:
            #     best_pos = Position(x, y)
            #     best_pos_halite = cell_halite_amount
            # logging.info("new best: {}, {}".format(best_pos, best_pos_halite))
    sorted_cells.sort(key=lambda tup: tup[1], reverse=True)
    return sorted_cells


def get_explore_dist(game_turn_number, game_map):
    MIN_EXPLORE_DIST = 10
    MAX_EXPLORE_DIST = game_map.height / 2
    return int(MIN_EXPLORE_DIST + game_turn_number / constants.MAX_TURNS * (MAX_EXPLORE_DIST - MIN_EXPLORE_DIST))


def navigate(game_map, ship, destination, is_final_return, shipyard_position):
    # Check wanted direction
    unsafe_moves = game_map.get_unsafe_moves(ship.position, destination)
    random.shuffle(unsafe_moves)
    for direction in unsafe_moves:
        target_pos = ship.position.directional_offset(direction)
        target_pos = game_map.normalize(target_pos)
        if target_pos not in ship_next_step_list or (is_final_return and target_pos == shipyard_position):
            ship_next_step_list.append(target_pos)
            return direction

    # target position is occupied. How about not moving?
    if ship.position not in ship_next_step_list:
        ship_next_step_list.append(ship.position)
        return Direction.Still

    # ship.position is still occupied! Wander move.
    safe_directions = []
    for direction in Direction.get_all_cardinals():
        pos = ship.position.directional_offset(direction)
        if pos not in ship_next_step_list:
            safe_directions.append(direction)

    # logging.info("navigate() wander ship:{}, destination:{}".format(ship.id, destination))
    if len(safe_directions) == 0:
        # Ready for collision
        return Direction.Still
    else:
        wander_direction = random.choice(safe_directions)
        target_pos = ship.position.directional_offset(wander_direction)
        ship_next_step_list.append(target_pos)
        # logging.info("safe_directions = {}, wander_direction = {}".format(safe_directions, wander_direction))
        return wander_direction


def get_naive_give_target_position(target_getter_count, ship, game_map, shipyard_position, game_turn_number):
    if target_getter_count % 4 == 0:
        x_multiplier, y_multiplier = 1, 1
    elif target_getter_count % 4 == 1:
        x_multiplier, y_multiplier = -1, 1
    elif target_getter_count % 4 == 2:
        x_multiplier, y_multiplier = 1, -1
    elif target_getter_count % 4 == 3:
        x_multiplier, y_multiplier = -1, -1
    else:
        raise Exception("error naive_give_direction()")

    best_pos = search_max_mine(game_map, game_turn_number, shipyard_position, x_multiplier, y_multiplier)

    # # Randon offset
    # random_offset_distribution = [-2, -1, -1, 0, 0, 0, 1, 1, 2]
    # best_pos.x += random.choice(random_offset_distribution)
    # best_pos.y += random.choice(random_offset_distribution)
    # best_pos = game_map.normalize(best_pos)

    logging.info("Ship {} get target position. cnt: {}. best_pos: {}".format(ship.id, target_getter_count, best_pos))
    # logging.info("Ship {} get target position. cnt: {}. x, xm, y, ym: {}, {}, {}, {}. target: {}, {}".format(ship.id, target_getter_count, x, x_multiplier, y, y_multiplier, x_target, y_target))
    target_getter_count += 1
    return target_getter_count, best_pos


def get_target_position(game_map, ship, sorted_cells, is_close, close_dist, shipyard_position):
    EXPLORE_RATE = 0
    current_targets = []
    for key, value in ship_target.items():
        current_targets.append(value)

    for pos_tuple in sorted_cells:
        pos = pos_tuple[0]

        if random.uniform(0, 1) < EXPLORE_RATE:
            continue

        if is_close:
            dist = game_map.calculate_distance(pos, ship.position)
            if dist > close_dist:
                continue

        if pos not in current_targets:
            logging.info("Ship {} get target position. best_pos: {}".format(ship.id, pos))
            return pos
    return shipyard_position


def move_ship_to_position(command_queue, game_map, ship, target_position, is_final_return, shipyard_position):
    move = navigate(game_map, ship, target_position, is_final_return, shipyard_position)
    command_queue.append(ship.move(move))
    return command_queue


def log_action(action, ship, game_map):
    logging.info("action: {}".format(action))
    logging.info("ship_status = {}".format(ship_status))
    logging.info("ship_target = {}".format(ship_target))
    logging.info("Ship {} has {} halite. gamemap[position]: halite={}".format(ship.id, ship.halite_amount, game_map[ship.position].halite_amount))


def is_exceed_mining_threshold(game_map, ship, game_turn_number):
    WAIT_FOR_MINING_THRESHOLD = 100
    if game_turn_number <= 200:
        return game_map[ship.position].halite_amount > WAIT_FOR_MINING_THRESHOLD
    else:
        return game_map[ship.position].halite_amount > WAIT_FOR_MINING_THRESHOLD * (game_turn_number - 200) / (constants.MAX_TURNS - 200)


while True:
    game.update_frame()
    me = game.me
    for player_id in range(len(game.players)):
        if game.my_id != player_id:
            enemy_id = player_id  # Find randomly one oppoent
            break
    logging.info("Targeted Enemy: {}".format(enemy_id))
    enemy = game.players[enemy_id]

    game_map = game.game_map

    # A command queue holds all the commands you will run this turn.
    command_queue = []
    ship_next_step_list = []

    # No energy ship makes decision first
    ships_will_be_stayed = []
    sorted_cells = search_max_mine_list(game_map, game.turn_number, me.shipyard.position, enemy.shipyard.position)

    # Stayed ships
    for ship in me.get_ships():
        # No energy
        if ship.halite_amount < game_map[ship.position].halite_amount / 10:
            ships_will_be_stayed.append(ship)
            command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)
            log_action("stay_still", ship, game_map)
        # Mine
        elif is_exceed_mining_threshold(game_map, ship, game.turn_number) and not ship.is_full and game.turn_number >= 5:
            ships_will_be_stayed.append(ship)
            command_queue = move_ship_to_position(command_queue, game_map, ship, ship.position, False, None)
            log_action("stay_still", ship, game_map)

    # Normal ships
    for ship in [ship for ship in me.get_ships() if ship not in ships_will_be_stayed]:
        logging.info("Ship {} has {} halite.".format(ship.id, ship.halite_amount))
        logging.info("ship_status = {}".format(ship_status))

        # init ship
        if ship.id not in ship_status:
            ship_status[ship.id] = STATE_EXPLORE
        if ship.id not in ship_target:
            ship_target[ship.id] = get_target_position(game_map, ship, sorted_cells, False, None, me.shipyard.position)

        # Final return
        if constants.MAX_TURNS - game.turn_number <= game_map.height * 0.75:
            command_queue = move_ship_to_position(command_queue, game_map, ship, me.shipyard.position, True, me.shipyard.position)
            log_action("Final return. to {}".format(me.shipyard.position), ship, game_map)
            continue

        # Explore/return
        if ship_status[ship.id] == STATE_RETURN:
            if ship.position == me.shipyard.position:
                ship_status[ship.id] = STATE_EXPLORE
                del ship_target[ship.id]
                ship_target[ship.id] = get_target_position(game_map, ship, sorted_cells, False, None, me.shipyard.position)
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                log_action("init explore. move to {}".format(ship_target[ship.id]), ship, game_map)
                continue
            else:
                command_queue = move_ship_to_position(command_queue, game_map, ship, me.shipyard.position, False, None)
                log_action("return move. to {}".format(me.shipyard.position), ship, game_map)
                continue
        elif ship_status[ship.id] == STATE_EXPLORE:
            if ship.halite_amount >= 250 + (constants.MAX_TURNS - game.turn_number) / constants.MAX_TURNS * 200:
                ship_status[ship.id] = STATE_RETURN
                command_queue = move_ship_to_position(command_queue, game_map, ship, me.shipyard.position, False, None)
                log_action("init return. move to {}".format(me.shipyard.position), ship, game_map)
                continue
            elif ship.position == ship_target[ship.id]:
                ship_target[ship.id] = get_target_position(game_map, ship, sorted_cells, True, 7, me.shipyard.position)
                log_action("change explore. move to {}".format(ship_target[ship.id]), ship, game_map)
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
            else:
                command_queue = move_ship_to_position(command_queue, game_map, ship, ship_target[ship.id], False, None)
                log_action("explore. move to {}".format(ship_target[ship.id]), ship, game_map)
                continue
        else:
            raise Exception("Unknown status {}".format(ship_status[ship.id]))

    if len(me.get_ships()) < MAX_NUM_SHIP and me.halite_amount >= constants.SHIP_COST and me.shipyard.position not in ship_next_step_list and (
            game.turn_number - last_build_turn) > BUILD_COOLDOWN and game.turn_number <= MAX_TURN_BUILD_SHIP:
        command_queue.append(game.me.shipyard.spawn())
        last_build_turn = game.turn_number

    logging.info("command_queue = {}".format(command_queue))
    game.end_turn(command_queue)
