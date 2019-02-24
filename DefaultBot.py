#!/usr/bin/env python3

# Import the Halite SDK, which will let you interact with the game.
import hlt
from hlt import constants
from hlt.positionals import *

import random
import logging

game = hlt.Game()
ship_status = {}
ship_explore_targets = {}
last_build_turn = -999


def find_target(game_map, ship):
    logging.info("game_map = {}".format(game_map))
    #    for x in range(game_map.width):
    #        for y in range(game_map.height):

    #            logging.info(game_map[Position(x, y)].halite_amount)
    #    for key in game_map:
    #        logging.info("key = {}".format(key))
    #    0/0

    return Position(random.choice(range(game_map.width)), random.choice(range(game_map.height)))


game.ready("MyPythonBot")

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
            ship_status[ship.id] = "exploring"
        if ship.id not in ship_explore_targets:
            ship_explore_targets[ship.id] = find_target(game_map, ship)

        if game_map[ship.position].halite_amount < constants.MAX_HALITE / 10 or ship.is_full:
            if ship_status[ship.id] == "returning":
                if ship.position == me.shipyard.position:
                    ship_status[ship.id] = "exploring"
                    command_queue.append(ship.move("o"))
                    continue
                else:
                    move = game_map.naive_navigate(ship, me.shipyard.position)
                    command_queue.append(ship.move(move))
                    continue
            else:
                if ship.halite_amount >= constants.MAX_HALITE / 4:
                    ship_status[ship.id] = "returning"
                    del ship_explore_targets[ship.id]
                    command_queue.append(ship.move("o"))
                    continue
                else:
                    move = game_map.naive_navigate(ship, ship_explore_targets[ship.id])
                    command_queue.append(ship.move(move))

            # if ship.id % 2 == 0:
            #     possible_directions = ["n", "e"]
            # else:
            #     possible_directions = ["s", "w"]
            # command_queue.append(
            #     ship.move(random.choice(possible_directions)))
        else:
            command_queue.append(ship.stay_still())

    if len(me.get_ships()) < 3 and me.halite_amount >= constants.SHIP_COST and not game_map[
        me.shipyard].is_occupied and (game.turn_number - last_build_turn) > 8:
        command_queue.append(game.me.shipyard.spawn())
        last_build_turn = game.turn_number

    # Send your moves back to the game environment, ending this turn.
    game.end_turn(command_queue)
