from datetime import timedelta

# A show can still be booked until this long after it starts.
LATE_BOOKING_WINDOW = timedelta(minutes=15)
