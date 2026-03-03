from BirdBrain import Finch
from typing import TypeAlias

Anchor: TypeAlias = tuple[float, float] # an anchor is a tuple of x and y coordinates
Line: TypeAlias = tuple[Anchor, Anchor] # a line is a tuple of two anchors

class Room_Map:
    # the finch object, used to get the current location of the finch and to update the location of the finch on the map
    finch_obj: Finch
    finch_x: float = 0
    finch_y: float = 0

    # the max and min x and y values of the room, used to determine the size of the map and to scale the map accordingly
    room_max_x: float = 1000
    room_max_y: float = 1000
    room_min_x: float = 1000
    room_min_y: float = 1000

    # the number of anchors and lines in the map, used to keep track of the number of anchors and lines in the map and to scale the map accordingly
    numOfAnchors: int = 0
    anchorList: list[Anchor] = []
    numOfLines: int = 0
    lineList: list[Line] = []

    def __init__(self, finch: Finch):
        self.finch_obj = finch
        # Placeholder for getting the initial location of the finch, will be updated in the future to reference the finch object directly
        # self.finch_x = finch_obj.get_x()
        # self.finch_y = finch_obj.get_y()
    
    def get_finch_location(self): # returns the current location of the finch as a tuple (x, y)
        return (self.finch_x, self.finch_y)
    
    def add_anchor(self, anchor: Anchor): 
        # adds an anchor to the map and sets its location to the current location of the finch
        self.anchorList.append(anchor)
        self.numOfAnchors += 1

    def update_finch_location(self, x: float, y: float): 
        # updates the current location of the finch on the map referencing the finch's actual location
        self.finch_x = x
        self.finch_y = y

    def draw_line(self, anchor1: Anchor, anchor2: Anchor): 
        # draws a line between two anchors and adds it to the line list
        self.lineList.append((anchor1, anchor2))
        self.numOfLines += 1
    
    def trace_path(self, x: float, y: float): 
        # a combination of the update_finch_location and draw_line functions
        # it updates the location of the finch and draws a line from the previous location to the new location
        prev_x = self.finch_x
        prev_y = self.finch_y
        self.update_finch_location(x, y)
        self.draw_line((prev_x, prev_y), (x, y))
        