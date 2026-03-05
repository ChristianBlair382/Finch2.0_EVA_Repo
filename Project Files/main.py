from RoomFinch import RoomFinch
from RoomNav import navigateRoom


def main():
    finch = RoomFinch()

    print("=== Room Mapping Finch ===")
    print("1 - Manual Control")
    print("2 - Automatic Navigation")
    choice = input("Select mode: ").strip()

    if choice == "1":
        finch.manualOverride()

    elif choice == "2":
        calibrate = input("Calibrate for floor surface? (y/n): ").strip().lower()

        if calibrate == "y":
            print("\nPlace the finch facing a wall, then press Enter to start calibration.")
            input()
            finch.calibrateFloor()
            print("\nPlease correct finch orientation to original positioning if necessary.\nPress Enter to start navigation...")
            input()

        print("\nStarting automatic navigation. Press 'm' at any time for manual override.\n")
        navigateRoom(finch)

    else:
        print("Invalid choice.")

    finch.stopAll()
    print("Program ended.")


if __name__ == "__main__":
    main()