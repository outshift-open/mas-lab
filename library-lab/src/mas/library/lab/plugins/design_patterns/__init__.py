#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Experimental design-pattern plugins for lab/testing (not OSS)."""

from mas.library.lab.plugins.design_patterns.voting import (  # noqa: F401
    DeterministicVotingPlugin,
)
from mas.library.lab.plugins.design_patterns.staged_debate import (  # noqa: F401
    DeterministicStagedDebatePlugin,
)
from mas.library.lab.plugins.design_patterns.supervised import (  # noqa: F401
    DeterministicSupervisedPlugin,
)
from mas.library.lab.plugins.design_patterns.verifier import (  # noqa: F401
    DeterministicVerifierPlugin,
)
