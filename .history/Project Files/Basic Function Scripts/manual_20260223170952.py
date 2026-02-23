from BirdBrain import Finch
import keyboard

myFinch = Finch()

while True:
    print(keyboard.read_key())
    if keyboard.read_key() == "a":
        myFinch.setTurn('L', 1, 50)
    elif keyboard.read_key() == "d":
        myFinch.setTurn('R', 1, 50)
    elif keyboard.read_key() == "w":
        