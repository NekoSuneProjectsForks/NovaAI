# NovaAI — maintenance cleanup branch

This branch is dedicated to removing fork-specific feature additions while retaining reusable stability, security, installation, and compatibility fixes.

> **Cleanup in progress.** The source still contains custom features until their code and dependencies have been removed and validated. Do not assume that VRM/MMD, singing, streaming overlays, autonomous games, or Neuro-style integrations have already been removed.

## Intended scope

Remove fork-specific additions such as VRM avatars and MMD dancing, singing and backing-track processing, autonomous Minecraft and other game agents, chat games, Neuro SDK extensions, and custom streaming overlays. Remove related UI routes, settings, documentation, assets, dependencies, and dead imports together.

Preserve independent fixes where still applicable, including XTTS/torchaudio native-import handling, torchcodec compatibility, SQLite recovery, installer robustness, updater URL normalization, UTF-8 CLI input handling, and general server error handling.

## Current status

- [x] Dedicated cleanup branch created from `main`.
- [x] README replaced with an accurate cleanup status instead of advertising features slated for removal.
- [ ] Audit source and history across branches.
- [ ] Remove feature implementations and integrations.
- [ ] Keep or transplant reusable fixes.
- [ ] Remove obsolete dependencies and configuration.
- [ ] Run startup, import, installation, and regression tests.
- [ ] Open a draft pull request for review; **do not merge**.

## Running and testing

Until the cleanup is complete, refer to the code and install scripts in this branch for the actual supported options. Do not deploy this branch as a feature-free release.

## Upstream and license

This is a maintenance fork of [CacheNetworks/NovaAI](https://github.com/cachenetworks/NovaAI). See [LICENSE](LICENSE).
