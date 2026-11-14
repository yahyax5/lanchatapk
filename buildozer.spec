[app]
title = LAN Chat
package.name = lanchat
package.domain = org.lanchat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 2.0
requirements = python3,kivy
orientation = portrait,landscape
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = True
android.api = 36
android.ndk = 29
android.accept_sdk_license = True
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 0
