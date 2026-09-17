# SignalX Video Intro + Section Transition

Added the user-provided SignalX bull video as:
- `assets/signalx-bull-intro.mp4`
- `assets/signalx-bull-intro-poster.jpg`

Behavior:
- Full 4-second muted intro on initial site load.
- About 0.8-second visual transition using the same video when switching sections.
- Current section is changed during the transition, then revealed by fade-out.
- No overlay over TradingView internals; the transition is a full-page layer only during navigation.
- Reduced-motion preference disables the intro/transition.
- Auto-deploy is not performed by this package.
