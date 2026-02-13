#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quickstart for user-side remote agent service with runtime skill installation.

Author: Silan Hu (silan.hu@u.nus.edu)
"""

from easyremote import RemoteAgentService, RemoteSkill


def build_voice_skill_payload() -> str:
    builder = RemoteSkill(
        name="voice-agent",
        namespace="assistant",
        gateway_address="127.0.0.1:8080",
    )

    @builder.voice(name="transcribe_live", languages=("zh-CN", "en-US"))
    def transcribe_live(audio):
        return audio

    return builder.export_pipeline(include_gateway=True)


def build_writer_skill_payload() -> str:
    builder = RemoteSkill(
        name="writer-agent",
        namespace="assistant",
        gateway_address="127.0.0.1:8080",
    )

    @builder.remote(name="summarize", languages=("zh-CN",))
    def summarize(text):
        return text

    return builder.export_pipeline(include_gateway=True)


def main() -> None:
    service = RemoteAgentService(
        user_id="alice",
        preferred_language="zh-CN",
        gateway_address="127.0.0.1:8080",
    )

    # Remote agent pushes skill payload to user software.
    service.install_skill(build_voice_skill_payload())
    print("installed skills:", service.list_skill_names())

    # Install another skill at runtime (no restart).
    service.install_skill(build_writer_skill_payload())
    print("capabilities:", service.list_capabilities(language="zh-CN"))

    # Run by reference syntax: skill/capability.
    print(
        "summary:",
        service.run_ref(
            "writer-agent/summarize",
            "磁盘满导致服务退化",
            target_user_id="alice",
        ),
    )


if __name__ == "__main__":
    main()
