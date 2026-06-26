//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
export const toTitleCase = (text: string) => {
  return text
    .replace(/[-_]+/g, " ")
    .split(" ")
    .map((s) => (s ? s[0].toUpperCase() + s.slice(1) : s))
    .join(" ");
};
