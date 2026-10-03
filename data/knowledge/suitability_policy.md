# Suitability Policy (illustrative bank rule set, rules-v1)

## Risk appetite rule
Each product has a risk level: low, medium or high. Capital protected notes with full protection are low. Dual currency deposits are medium. Equity linked notes are high when the barrier is above 60%, medium when it is above 50% and up to 60%, and low when the barrier is at or below 50% (deep buffer). A customer with conservative appetite can hold low products, moderate can hold up to medium, aggressive can hold high. One level above the customer's appetite needs review; two levels above is a mismatch.

## Loss tolerance rule
The modeled tail loss is the larger of the worst historical rolling-window loss and the Monte Carlo 1st-percentile loss. If the tail loss is within the customer's loss tolerance the rule passes. Up to 1.5 times the tolerance needs review. Above that it is a mismatch.

## Horizon rule
The product tenor must not be longer than the customer's investment horizon. A longer tenor is a mismatch.

## Concentration rule
Existing exposure to the same underlying plus the new investment as a share of the portfolio must not exceed 50%. Above the limit is a mismatch.

## Repair guidance
To clear a flag, reduce the notional, lower the barrier, or shorten the tenor. Changes are checked again by the same rules before being suggested.
