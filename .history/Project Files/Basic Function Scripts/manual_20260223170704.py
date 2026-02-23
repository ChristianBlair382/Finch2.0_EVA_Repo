from BirdBrain import Finch
import keyboard

while True:
  
    print(keyboard.read_key())
    if keyboard.read_key() == "a":
        break