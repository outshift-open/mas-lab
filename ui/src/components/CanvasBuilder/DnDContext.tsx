//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useState, type ReactNode } from "react";
import type { DnDNodeType } from "./types";

type DnDContextType = [DnDNodeType, (type: DnDNodeType) => void];

const DnDContext = createContext<DnDContextType>([null, () => {}]);

export function DnDProvider({ children }: { children: ReactNode }) {
  const [type, setType] = useState<DnDNodeType>(null);
  return (
    <DnDContext.Provider value={[type, setType]}>
      {children}
    </DnDContext.Provider>
  );
}

export function useDnD() {
  return useContext(DnDContext);
}
