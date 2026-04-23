from Lib.RoomFinch import RoomFinch
from RoomNav import navigateRoom, manualOverride


def main():
    finch = RoomFinch('A')  # Initialize Finch on port B

    print("=== Room Mapping Finch ===")
    print("1 - Manual Control")
    print("2 - Automatic Navigation")
    print("3 - Set Turn Scale Manually")
    choice = input("Select mode: ").strip()

    if choice == "1":
        manualOverride(finch)

    elif choice == "2":
        calibrate = input("Calibrate for floor surface? (y/n): ").strip().lower()

        if calibrate == "y":
            print("\nPlace the finch facing a wall, then press Enter to start calibration.")
            input()
            finch.calibrateFloor()
            print("\nPlease correct finch orientation to original positioning if necessary.\nPress Enter to start navigation...")
            input()

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