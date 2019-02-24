# halite3_michaelwan_bot
## Overview
My (Michael Wan) attempt on halite 3 competition. 

It is developed in 1.5 weeks only and the highest rank is 18 (during first a few weeks), then abondoned and dropped to #183 finally. 

Although it didn't win, it only have ~700 lines of codes, which consist of main components like destination selection, collision/move strategies, dropoff/spawn strategies, etc.

Halite Profile: https://halite.io/user/?user_id=373

## Pesudo code of main logic

```
for each turn:
    value_map = calculate_value_map()
    stats = calculate_other_stats()
    
    prioritized_ships = ShipSelection.sort(ships)
    for each prioritized_ships:
        move = ship.get_move_by_status(
            status, 
            DestinationSelectionModule(value_map, stats), 
            MiningStrategy, DropoffStrategy
        )
        MoveModule.execute_move(move)
    ShipSpawningModule.build_ship()
```