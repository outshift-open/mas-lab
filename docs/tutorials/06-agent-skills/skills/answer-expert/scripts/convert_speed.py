#!/usr/bin/env python3
import json
import sys
from decimal import Decimal, ROUND_HALF_UP


metres_per_second = Decimal(sys.argv[1])
kilometres_per_second = metres_per_second / Decimal("1000")
miles_per_second = metres_per_second / Decimal("1609.344")

print(
    json.dumps(
        {
            "kilometres_per_second": str(kilometres_per_second),
            "miles_per_second": str(
                miles_per_second.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            ),
        }
    )
)