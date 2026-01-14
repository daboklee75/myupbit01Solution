import pyupbit
import pprint

print("Fetching ticks for KRW-BTC...")
ticks = pyupbit.get_tick("KRW-BTC", count=5)
if ticks:
    print("First tick data:")
    pprint.pprint(ticks[0])
else:
    print("No ticks found.")
