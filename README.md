# NovaAI — maintenance cleanup branch

This branch is dedicated to removing fork-specific feature additions while retaining reusable stability, security, installation, and compatibility fixes.

> **Cleanup in progress.** The identified VRM/MMD, singing, streaming overlay, and game integrations have been removed from the principal application modules. This branch has not passed startup or regression testing, and the commit history still needs a full fixes-versus-features audit.

## Intended scope

Remove fork-specific additions such as VRM avatars and MMD dancing, singing and backing-track processing, autonomous Minecraft and other game agents, chat games, Neuro SDK extensions, and custom streaming overlays. Remove related UI routes, settings, documentation, assets, dependencies, and dead imports together.

Preserve independent fixes where still applicable, including XTTS/torchaudio native-import handling, torchcodec compatibility, SQLite recovery, installer robustness, updater URL normalization, UTF-8 CLI input handling, and general server error handling.

## Current status

- [x] Dedicated cleanup branch created from `main`.
- [x] README replaced with an accurate cleanup status instead of advertising features slated for removal.
- [ ] Audit source and history across branches.
- [x] Remove identified avatar, MMD, singing, streaming and autonomous-game implementations and integrations.
- [ ] Keep or transplant reusable fixes.
- [x] Remove identified feature-only dependencies, settings and installer hooks.
- [ ] Run startup, import, installation, and regression tests.
- [ ] Open a draft pull request for review; **do not merge**.

## Running and testing

Do not deploy this branch until syntax, import, startup and regression tests pass. The maintenance branch is deliberately unmerged.

## Upstream and license

This is a maintenance fork of [CacheNetworks/NovaAI](https://github.com/cachenetworks/NovaAI). See [LICENSE](LICENSE).
