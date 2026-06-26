//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useState, type ReactNode } from "react";
import type { DnDPipelineNodeType } from "./types";

type DnDContextType = [DnDPipelineNodeType, (type: DnDPipelineNodeType) => void];

const DnDContext = createContext<DnDContextType>([null, () => {}]);

export function DnDProvider({ children }: { children: ReactNode }) {
  const [type, setType] = useState<DnDPipelineNodeType>(null);
  return (
    <DnDContext.Provider value={[type, setType]}>
      {children}
    </DnDContext.Provider>
  );
}

export function useDnD() {
  return useContext(DnDContext);
}
