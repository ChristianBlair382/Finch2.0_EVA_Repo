from BirdBrain import Finch
import time

myFinch = Finch()

for i in range(32,135):
    myFinch.playNote(i, 0.5)

myFinch.stopAll()
