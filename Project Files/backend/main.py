from Lib.RoomFinch import RoomFinch
from RoomNav import navigateRoom, ManualController

def main():
    USE_PID = True
    finch = RoomFinch('B', usePID = USE_PID)  # Initialize Finch on port A

    finch.stop()  # Ensure Finch is stopped before starting

    print("=== Room Mapping Finch ===")
    print("1 - Manual Control")
    print("2 - Automatic Navigation")
    print("3 - Set Turn Scale Manually")
    choice = input("Select mode: ").strip()

    if choice == "1":
        # Manual control is now driven by the frontend over SocketIO; this
        # path just instantiates the controller and idles. When a frontend
        # is wired up, this is where you'd start the Flask-SocketIO server
        # and bind controller methods to socket events.
        controller = ManualController(finch)
        print("\nManual mode active (no frontend wired up — use Ctrl-C to exit).")
        print("Available commands on the controller object:")
        print("  forward(), backward(), left(), right(), stop(),")
        print("  scan_anchor(), anchor_at_robot_position(), shutdown()")
        try:
            while True:
                # Idle. Frontend (or attached REPL) drives controller methods.
                import time
                time.sleep(0.1)
        except KeyboardInterrupt:
            controller.shutdown()

    elif choice == "2":
        #calibrate = input("Calibrate for floor surface? (y/n): ").strip().lower()

        #if calibrate == "y":
        #    print("\nPlace the finch facing a wall, then press Enter to start calibration.")
        #    input()
        #    finch.calibrateFloor()
        #    print("\nPlease correct finch orientation to original positioning if necessary.\nPress Enter to start navigation...")
        #    input()

        print("\nStarting automatic navigation.\n")
        navigateRoom(finch)

    elif choice == "3":
        scaleInput = input("Enter turn scale factor (e.g. 1.0 for default): ").strip()
        try:
            scale = float(scaleInput)
            finch.setTurnScale(scale)
            print(f"Turn scale set to {scale}, starting navigation.")
            navigateRoom(finch)
        except ValueError:
            print("Invalid input. Turn scale must be a number.")
    else:
        print("Invalid choice.")

    finch.stopAll()
    print("Program ended.")


if __name__ == "__main__":
    main()