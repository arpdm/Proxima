# Growth and Expansion Analysis

1. Lifetime expiration
2. Science production rate increase **[Implemented]**
3. Slow down resource deplition rate.
4. Static Buffer based servicing and expansion = Limit on all queues. Create queue fullness assessment.
5. Power deficit profile based on expansion.

## Expansion triggers

When adding capabilities, dont just give more power generation. Rules can be added, so the system can grow based on advancement needs or worldy events.

- Advancement
- Adding cpabilities
- Trying to advance to the next phase as fast as possible. Keeping velocity hight. Regulations and goals bring it down. They regulated advancement velocity.
- Human Growth
- Monetary needs to perform tasts
- Low material stock compraed to goals

## Expansion Rules

- Each zone has a growth limit (maybe based on entropy index). If a zone reaches the entropy index, another zone must be created. No central governence. Zones can regulate eachother.

## Expansion Policy 001

1. The policy engine decides to double the science generation rate
2. To meet the rate, new science rovers are requested from the construction sector.
3. Creation of rovers requires more enegry.
4. Energy deficit profile causes growth of energy sector.

## Report and Progress Notes

### Dec 7, 2025

There are few policies implemented already:

1. Industrial Dust Coverage Policy
2. Science Generate Growth Rate Policy

Before more policies are implemented and system grows in sophistication, following needs to happen:

1. Implement and setup the complexity engine
2. Run experiments, generate reports and analyze the system for policy implementation performance
3. Keep adding system policies and perform optimization until the 2 policies implemented perfom to expectations.

To achieve #3 following probabily will need to happen:

1. Find different ways to reduce dust coverage. Throttling alone will not be enough as system grows.
2. Avoid unlimited growth. Growth needs to be controlled based on : (Industrial Dust Coverage Reduction, Resource Depletion, Entropy Index)

#### Analysis Observations

After initial analysis, seems like the rovers are being requested for growth in duplicate amounts. Rovers need to be requested every 4320 steps. It means that in 10000 steps, only two times there needs to be pipeline request. 

Take a better look at the calculation of how many rovers are needed to meet the need for growth. 

Another observation is that even if we have 90 rovers, only 20 of them are operational. So why should we keep asking for more rovers if utilization is low. Maybe the policy needs to be modified so that rovers are requested if utilization is high. otherwise, keep track of the needed rovers vs requested rover to know that we need specific amount for growth but since utilization is low, they are not being requested.
