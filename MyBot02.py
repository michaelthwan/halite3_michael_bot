#!/usr/bin/env python3

# Import the Halite SDK, which will let you interact with the game.
import hlt
from hlt import constants
from hlt.positionals import *

import random
import logging

game = hlt.Game()
ship_status = {}
last_build_turn = -999

STATE_EXPLORE = "explore"
STATE_RETURN = "return"
STATE_MINE = "mine"

MAX_NUM_SHIP = 3
BUILD_COOLDOWN = 5

game.ready("MyPythonBot")


def get_naive_give_direction(ship):
    if ship.id % 4 == 0:
        return ["n", "e"]
    elif ship.id % 4 == 1:
        return ["s", "w"]
    elif ship.id % 4 == 2:
        return ["s", "e"]
    elif ship.id % 4 == 3:
        return ["n", "w"]
    else:
        raise Exception("error naive_give_direction()")


while True:
    game.update_frame()
    me = game.me
    game_map = game.game_map

    # A command queue holds all the commands you will run this turn.
    command_queue = []

    for ship in me.get_ships():
        logging.info("Ship {} has {} halite.".format(ship.id, ship.halite_amount))
        logging.info("ship_status = {}".format(ship_status))
        logging.info("ship_explore_targets = {}".format(ship_status))

        if ship.id not in ship_status:
            ship_status[ship.id] = STATE_EXPLORE

        if game_map[ship.position].halite_amount > constants.MAX_HALITE / 10 and not ship.is_full:
            command_queue.append(ship.stay_still())
            continue
        else:
            if ship_status[ship.id] == STATE_RETURN:
                if ship.position == me.shipyard.position:
                    ship_status[ship.id] = STATE_EXPLORE
                    command_queue.append(ship.move("o"))
                    continue
                else:
                    move = game_map.naive_navigate(ship, me.shipyard.position)
                    command_queue.append(ship.move(move))
                    continue
            elif ship_status[ship.id] == STATE_EXPLORE:
                if ship.halite_amount >= constants.MAX_HALITE / 4:
                    ship_status[ship.id] = STATE_RETURN
                    move = game_map.naive_navigate(ship, me.shipyard.position)
                    # command_queue.append(ship.move("o"))
                    continue
                else:
                    possible_directions = get_naive_give_direction(ship)
                    command_queue.append(ship.move(random.choice(possible_directions)))
                    continue
            else:
                raise Exception("Unknown status {}".format(ship_status[ship.id]))

    if len(me.get_ships()) < MAX_NUM_SHIP and me.halite_amount >= constants.SHIP_COST and not game_map[me.shipyard].is_occupied and (game.turn_number - last_build_turn) > BUILD_COOLDOWN:
        command_queue.append(game.me.shipyard.spawn())
        last_build_turn = game.turn_number

    game.end_turn(command_queue)
