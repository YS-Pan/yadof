# Module blueprint: config

`yadof.config` owns generic defaults and returns immutable `LoadedConfig`. It merges
package defaults, workspace root `config.py`, then non-mutating call overrides.
Unknown uppercase names and invalid values fail eagerly. Relative paths resolve from
the selected workspace. Task shape and simulator-specific behavior remain task
files or supported environment strings, not framework global modules.
