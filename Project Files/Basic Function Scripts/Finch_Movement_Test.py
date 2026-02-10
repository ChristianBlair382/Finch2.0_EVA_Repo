from BirdBrain import Finch
import time

myFinch = Finch()

# This program demonstrates the Finch's ability to move using its motor
# functions.

# Do a 360 degree turn.
myFinch.setTurn('R', 180, 50)
myFinch.setTurn('R', 180, 50)

# Move forward and backward and then do a 90 degree turn 4 times.
for i in range(0, 4):
    myFinch.setMove('F', 10, 40)
    myFinch.setMove('B', 10, 40)
    myFinch.setTurn('R', 90, 30)

myFinch.stopAll()
