# FarSight Reference Architecture v0.1
## Photonic Dandelion Interstellar Relay Corridor — Earth to Proxima b

**Status:** Baseline architecture frozen for first-order systems modelling  
**Purpose:** Determine whether the orders of magnitude close before introducing further architectural changes.

**Primary modelling question**

> Can periodically launched swarms of ultra-light photonic probes create a survivable, regenerative optical communications corridor from the Solar System to Proxima b at a plausible total mass, energy, launch cadence, and end-to-end science throughput?

This document does **not** claim feasibility. It freezes the architecture to be tested.


## 1. Architecture summary

The baseline concept is:

> **Mass-produce ultra-light photonic “dandelion” probes, launch them in periodic swarms, externally accelerate them to relativistic cruise speed, use their multifunction photonic membranes as propulsion surfaces and optical communications apertures, and progressively build a redundant regenerative relay corridor between Earth and Proxima b.**

Each probe is designed more like an artificial seed than a conventional spacecraft:

- extremely low mass;
- very large area-to-mass ratio;
- little or no onboard propulsion;
- external photon-driven acceleration;
- passive or quasi-passive stability where possible;
- long dormancy periods;
- burst communications;
- mass manufacturing;
- high tolerated individual failure rate;
- swarm-level redundancy.


## 2. Mission topology

```text
EARTH / SOLAR SYSTEM
        │
        ▼
RELAY SWARM 0
        │  regenerative optical hop
        ▼
RELAY SWARM 1
        │
       ...
        │
        ▼
FINAL RELAY / SCIENCE SWARM
        │
        ▼
PROXIMA b / PROXIMA SYSTEM
```

Each relay performs:

```text
receive → detect → decode/error-correct → store → route/schedule → retransmit
```

Baseline: **active regenerative relaying**, not passive reflection.


## 3. Fleet baseline

```yaml
fleet:
  total_probes: 1_000_000
  relay_swarms: 1_000
  probes_per_swarm: 1_000
```

Nominal route length:

```yaml
route_distance_ly: 4.24
route_distance_au: ~268_000
```

FarSight should source the precise value from authoritative astronomical data rather than hard-code the approximation.

For 1,000 equally spaced relay positions:

```yaml
nominal_spacing_au: ~268
```

Relay spacing remains an optimization variable.


## 4. Launch and cruise

Baseline sequence:

```text
Earth launch
  → carrier / deployment stage
  → inner-Solar-System deployment
  → swarm release
  → solar-photon deployment / passive stabilization
  → external beamed-energy acceleration
  → relativistic cruise
```

Cruise-speed scenarios:

```yaml
cruise_speed_fraction_c:
  min: 0.05
  low: 0.10
  baseline: 0.20
  high: 0.30
```

At fixed speed and equal spacing:

```text
launch interval = relay spacing / cruise speed
```

The baseline 0.2c / ~268 AU case implies roughly **one swarm every 7.8 days**. Treat this as derived, not independent.


## 5. Probe architecture

### Core principle

The membrane should perform as many functions as possible:

- acceleration surface;
- optical transmit aperture;
- optical receive aperture;
- structural element;
- passive attitude stabilization;
- possibly beam steering;
- possibly photovoltaic generation near stars.

### Membrane diameter

```yaml
membrane_diameter_m:
  min: 0.10
  baseline: 0.50
  stretch: 1.00
```

### Probe mass

Do **not** assume one validated value. Decompose:

```yaml
probe_mass:
  membrane: TBD
  compute_and_control: TBD
  optical_tx_rx: TBD
  power_source: TBD
  energy_storage: TBD
  sensors: TBD
  structure_and_interconnect: TBD
  shielding_or_sacrificial_layer: TBD
```

Exploratory total-mass cases:

```yaml
probe_mass_g:
  aggressive: 0.01
  intermediate: 0.10
  conservative: 1.00
```

These are scenario values, not claims of current feasibility.

Derived:

```text
areal_density = total_probe_mass / membrane_area
```


## 6. Communications

Baseline:

```yaml
communications:
  type: optical
  wavelength_nm: 1550
  relay_mode: regenerative
  target_data_rate_bps: 1_000
```

Cooperative swarm modes:

```yaml
swarm_communications_mode:
  baseline: noncoherent_cooperative
  stretch: phase_coherent
```

Do **not** assume perfect phase coherence in the baseline.

Per-probe burst transmit-power scenarios:

```yaml
optical_tx_power_w:
  min: 0.001
  baseline: 0.10
  max: 1.00
```

Data-rate scenarios:

```yaml
relay_data_rate_bps:
  low: 10
  baseline: 1_000
  high: 100_000
```

Minimum link outputs:

- photons received per bit;
- detector/SNR margin;
- coding margin;
- achievable rate;
- energy per delivered bit;
- retransmission burden;
- relay availability;
- bottleneck relay position.


## 7. Power architecture

Operating concept:

```text
deep dormancy
  → slow energy accumulation
  → scheduled wake / beacon acquisition
  → receive / decode / store
  → burst retransmission
  → dormancy
```

Continuous high-power operation is rejected.

Generic long-duration source:

```yaml
power_source:
  type: long_duration_micro_power
  initial_power_w: TBD
  degradation_model: TBD
```

Energy storage:

```yaml
energy_storage:
  usable_energy_j: TBD
  specific_energy_wh_per_kg: TBD
  calendar_degradation: TBD
  self_discharge: TBD
```

The key quantity is **stored joules required per relay event**, not only average cruise power.


## 8. Science payload

### Relay probes
Minimum:
- optical communications;
- timing;
- acquisition / relative navigation;
- health/status;
- minimal environmental sensing if mass permits.

### Final science swarm
Candidate classes:
- visible / NIR imaging;
- low-resolution spectroscopy;
- particle / plasma sensing;
- magnetometry;
- radiation / dust sensing;
- stellar / planetary environment observations.

Science payload is not yet frozen because infrastructure feasibility is the first question.


## 9. Navigation and pointing

Likely dominant constraint.

Model:

```yaml
navigation:
  absolute_position_error: TBD
  relative_swarm_position_error: TBD
  velocity_dispersion: TBD
  clock_error: TBD
  pointing_error_rad: TBD
  beam_steering_range: TBD
```

Prefer:
- passive photonic stabilization;
- minimal active control;
- electronic / photonic beam steering.

Do not assume conventional reaction wheels, star trackers, or formation-keeping propulsion unless explicitly introduced as a variant.


## 10. Reliability and attrition

Do not begin with one fixed survival probability.

Separate:

### Aleatory
Where defensible:
- manufacturing variation;
- detector noise;
- stochastic particle impacts.

### Epistemic
Likely:
- 20-year membrane degradation;
- relativistic dust tails;
- long-duration micro-power reliability;
- common-mode manufacturing defects.

Common-mode failure is mandatory.

Examples:
- production-batch membrane defect;
- firmware defect affecting one generation;
- accelerator mis-pointing affecting an entire swarm;
- protocol incompatibility between generations;
- environmental event affecting many adjacent probes.

Do **not** assume independent Bernoulli failures.

Define:

```yaml
minimum_operational_probes_per_swarm: TBD
```

FarSight should derive this from link requirements.


## 11. Interstellar environment

At minimum model uncertainty in:

- gas density;
- dust particle distribution;
- dust-impact rate;
- membrane erosion;
- radiation;
- charging;
- thermal environment;
- velocity-dependent damage.

Measured constraints and speculative extrapolations must remain separate.


## 12. Generation compatibility

Because deployment lasts decades, later swarms may improve.

Allow:

```yaml
probe_generation:
  gen_1: {}
  gen_2: {}
  gen_3: {}
```

Generations may differ in detector sensitivity, laser efficiency, coding, compute, clock stability, power, or membrane properties.

Interoperability across generations is a system requirement.


## 13. Optimization variables

At minimum:

```text
N_total_probes
N_swarms
N_probes_per_swarm
relay_spacing
launch_interval
cruise_speed
probe_mass
membrane_diameter
membrane_areal_density
optical_tx_power
optical_efficiency
receiver_efficiency
wavelength
beam_divergence
pointing_error
data_rate
energy_storage
long_duration_power
probe_survival
common_mode_failure_strength
minimum_live_probes_per_swarm
science_data_volume
```

Constraint:

```text
N_total_probes = N_swarms × N_probes_per_swarm
```


## 14. Objective functions

Do not force a single optimum.

Evaluate a Pareto frontier across:

1. **Science:** maximize science bits returned to Earth.
2. **Infrastructure:** maximize end-to-end communications availability.
3. **Mass:** minimize total accelerated mass.
4. **Energy:** minimize accelerator + relay energy per returned bit.
5. **Reliability:** maximize robustness under admissible uncertainties.
6. **Technology readiness:** minimize dependence on unvalidated assumptions.


## 15. Core model outputs

The first systems model should report:

1. total accelerated mass;
2. total membrane area;
3. swarm count;
4. probes per swarm;
5. relay spacing;
6. launch cadence;
7. accelerator duty cycle;
8. per-hop link margin;
9. achievable relay rate;
10. energy per relay packet;
11. energy per science bit delivered to Earth;
12. stored energy required per probe;
13. minimum surviving probes per relay;
14. end-to-end throughput;
15. end-to-end latency;
16. total deployment time;
17. relay-availability envelope;
18. sensitivity to common-mode failures;
19. sensitivity to pointing error;
20. sensitivity to membrane degradation;
21. dominant feasibility constraints;
22. assumptions most strongly determining viability;
23. experiments or measurements that would most reduce uncertainty.


## 16. Initial scenario matrix

### Cruise speed
```text
0.05c
0.10c
0.20c
0.30c
```

### Probe mass
```text
0.01 g
0.10 g
1.00 g
```

### Membrane diameter
```text
0.10 m
0.50 m
1.00 m
```

### Swarm structure
```text
100 swarms × 10,000 probes
1,000 swarms × 1,000 probes
10,000 swarms × 100 probes
```

### Relay data target
```text
10 bps
1 kbps
100 kbps
```


## 17. Assumptions that must remain visible

The following are **not established facts**:

1. A useful probe can be built in the mg–g regime with a 0.5–1 m membrane.
2. Such a membrane can survive relativistic cruise.
3. The membrane can serve as propulsion surface and high-gain optical aperture.
4. Passive photonic stability can meet pointing requirements.
5. Long-duration micro-power can meet mass and reliability constraints.
6. Cooperative swarm communication yields useful gain without impossible synchronization.
7. A reusable accelerator can sustain the required 0.1–0.2c swarm launch cadence.
8. Relay geometry remains predictable enough over decades.
9. Common-mode attrition does not remove multiple adjacent relay swarms.
10. Useful final science throughput remains after relay overhead and losses.

FarSight must never silently convert these into certainties.


## 18. Frozen baseline v0.1

```yaml
mission:
  destination: Proxima_b
  distance_ly: 4.24

fleet:
  total_probes: 1_000_000
  relay_swarms: 1_000
  probes_per_swarm: 1_000

trajectory:
  cruise_speed_fraction_c: 0.20

probe:
  membrane_diameter_m: 0.50
  total_mass_g: 0.10  # exploratory placeholder, not validated

communications:
  wavelength_nm: 1550
  relay_type: regenerative_optical
  swarm_mode: noncoherent_cooperative
  optical_tx_power_w_per_probe: 0.10
  target_data_rate_bps: 1_000

operations:
  mode: dormant_with_burst_relay

uncertainty:
  epistemic_aleatory_separation_required: true
  common_mode_failures_required: true
```

Derived values such as relay spacing and launch cadence must be computed, not duplicated manually.


## 19. First FarSight question

Do **not** optimize immediately.

Run the frozen v0.1 baseline first and answer:

> **Which five assumptions dominate whether the architecture closes at all?**

For each dominant assumption report:

1. baseline value or admissible range;
2. provenance / confidence;
3. sensitivity of mission viability;
4. threshold at which the architecture fails;
5. aleatory vs epistemic classification;
6. the experiment, measurement, or technology milestone that would reduce uncertainty most.

Only then begin optimization.


## 20. Architecture discipline

Until the first baseline run is complete:

> **Do not change the architecture merely because a new idea appears attractive.**

Log new ideas as candidate variants.

A variant replaces v0.1 only if the model identifies a specific bottleneck and the change directly addresses it.

This preserves falsifiability and prevents conceptual drift.
