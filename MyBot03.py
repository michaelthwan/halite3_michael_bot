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
last_build_turn = -999
target_getter_count = 0

STATE_EXPLORE = "explore"
STATE_RETURN = "return"
STATE_MINE = "mine"

MAX_NUM_SHIP = 3
BUILD_COOLDOWN = 5
EXPLORE_DIST = 20

game.ready("MyPythonBot")


def get_naive_give_target_position(target_getter_count, ship, game_map, shipyard_position):
    x = shipyard_position.x
    y = shipyard_position.y

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

    x_target = x + random.choice(range(EXPLORE_DIST)) * x_multiplier
    y_target = y + random.choice(range(EXPLORE_DIST)) * y_multiplier
    target_getter_count += 1
    logging.info("Ship {} get target position. cnt: {}. x, xm, y, ym: {}, {}, {}, {}. target: {}, {}".format(ship.id, target_getter_count, x, x_multiplier, y, y_multiplier, x_target, y_target))
    return target_getter_count, Position(x_target, y_target)


def move_ship_to_position(command_queue, ship, target_position):
    move = game_map.naive_navigate(ship, target_position)
    command_queue.append(ship.move(move))
    return command_queue


def log_action(action, ship, game_map):
    logging.info("action: {}".format(action))
    logging.info("ship_status = {}".format(ship_status))
    logging.info("ship_target = {}".format(ship_target))
    logging.info("Ship {} has {} halite. gamemap[position]: halite={}".format(ship.id, ship.halite_amount, game_map[ship.position].halite_amount))


while True:
    game.update_frame()
    me = game.me
    game_map = game.game_map

    # A command queue holds all the commands you will run this turn.
    command_queue = []

    for ship in me.get_ships():
        logging.info("Ship {} has {} halite.".format(ship.id, ship.halite_amount))
        logging.info("ship_status = {}".format(ship_status))

        # init ship
        if ship.id not in ship_status:
            ship_status[ship.id] = STATE_EXPLORE
        if ship.id not in ship_target:
            target_getter_count, ship_target[ship.id] = get_naive_give_target_position(target_getter_count, ship, game_map, me.shipyard.position)

        # No energy
        if ship.halite_amount < game_map[ship.position].halite_amount / 10:
            command_queue.append(ship.stay_still())
            log_action("stay_still", ship, game_map)
            continue

        # Mine
        if game_map[ship.position].halite_amount > constants.MAX_HALITE / 10 and not ship.is_full:
            command_queue.append(ship.stay_still())
            log_action("stay_still", ship, game_map)
            continue

        # Explore/return
        if ship_status[ship.id] == STATE_RETURN:
            if ship.position == me.shipyard.position:
                ship_status[ship.id] = STATE_EXPLORE
                del ship_target[ship.id]
                target_getter_count, ship_target[ship.id] = get_naive_give_target_position(target_getter_count, ship, game_map, me.shipyard.position)
                command_queue = move_ship_to_position(command_queue, ship, ship_target[ship.id])
                log_action("init explore. move to {}".format(ship_target[ship.id]), ship, game_map)
                continue
            else:
                command_queue = move_ship_to_position(command_queue, ship, me.shipyard.position)
                log_action("return move. to {}".format(me.shipyard.position), ship, game_map)
                continue
        elif ship_status[ship.id] == STATE_EXPLORE:
            if ship.halite_amount >= constants.MAX_HALITE / 4:
                ship_status[ship.id] = STATE_RETURN
                command_queue = move_ship_to_position(command_queue, ship, me.shipyard.position)
                log_action("init return. move to {}".format(me.shipyard.position), ship, game_map)
                continue
            elif ship.position == ship_target[ship.id]:
                target_getter_count, ship_target[ship.id] = get_naive_give_target_position(target_getter_count, ship, game_map, me.shipyard.position)
                log_action("change explore. move to {}".format(ship_target[ship.id]), ship, game_map)
                command_queue = move_ship_to_position(command_queue, ship, ship_target[ship.id])
            else:
                command_queue = move_ship_to_position(command_queue, ship, ship_target[ship.id])
                log_action("explore. move to {}".format(ship_target[ship.id]), ship, game_map)
                continue
        else:
            raise Exception("Unknown status {}".format(ship_status[ship.id]))

    if len(me.get_ships()) < MAX_NUM_SHIP and me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied and (game.turn_number - last_build_turn) > BUILD_COOLDOWN:
        command_queue.append(game.me.shipyard.spawn())
        last_build_turn = game.turn_number

    logging.info("command_queue = {}".format(command_queue))
    game.end_turn(command_queue)
