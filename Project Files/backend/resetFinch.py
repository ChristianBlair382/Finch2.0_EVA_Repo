from Lib.RoomFinch import RoomFinch
import time

finch = RoomFinch('A', usePID=True)
finch.stop()
finch._finch.setTail("all",0,0,0)
finch._finch.setBeak(0,0,0)