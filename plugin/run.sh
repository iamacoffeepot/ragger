#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export JAVA_HOME="$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home"
export RAGGER_PROJECT_ROOT="$(cd .. && pwd)"
./gradlew run
