# Repeated observation resources

`tests/live_resource_stress.py` performs 28 inspections of a 520-control GTK window, returning 500 nodes per inspection, and captures a 640-pixel-wide screenshot each iteration. It checks the 4,000-element and 16-snapshot cache bounds, stable file-descriptor count after warm-up, and absence of helper descendants after each request. Closing the backend must clear both caches and release its lock descriptor.

The ARM64 private Xvfb/XFWM run passed. The observed final resident set was approximately 34 MiB, with four descriptors after close. The test reports all samples and allows up to 128 MiB spread during the repeated phase to catch gross growth without confusing allocator warm-up with leakage. That threshold is a regression threshold, not a product memory ceiling.

This is a short repeated-load regression, not hours-long endurance testing, external process accounting, or a guarantee under every application tree. It is included in the isolated headless runner and retains source/environment evidence there.
