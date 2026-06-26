//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { createContext, useContext } from "react";

const NamespaceContext = createContext<string>("global");

export const NamespaceProvider = NamespaceContext.Provider;

export function useNamespace(): string {
  return useContext(NamespaceContext);
}
