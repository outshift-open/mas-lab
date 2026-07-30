//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { PageWithTitle, CodeBlock } from "@/components";
import {
  Box,
  CircularProgress,
  Typography,
  useTheme,
  Button,
} from "@mui/material";
import { useNavigate, useParams } from "react-router";
import { useCallback, useMemo, useState } from "react";
import {
  useExperimentDetail,
  fetchExperimentFile,
  API_BASE_URL,
  type FileTreeEntry,
} from "@/api/apiCalls";
import {
  FolderOpen as FolderIcon,
  InsertDriveFileOutlined as FileIcon,
  ExpandMore as ExpandMoreIcon,
  ChevronRight as ChevronRightIcon,
} from "@mui/icons-material";
import {
  Panel,
  Group as PanelGroup,
  Separator as PanelResizeHandle,
} from "react-resizable-panels";

function getLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    json: "json",
    jsonl: "json",
    yaml: "yaml",
    yml: "yaml",
    csv: "csv",
    md: "markdown",
    html: "html",
    txt: "plaintext",
    py: "python",
  };
  return map[ext] ?? "plaintext";
}

interface TreeNodeProps {
  entry: FileTreeEntry;
  path: string;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  depth?: number;
}

function TreeNode({
  entry,
  path,
  selectedPath,
  onSelect,
  depth = 0,
}: TreeNodeProps) {
  const [expanded, setExpanded] = useState(true);
  const isDir = entry.type === "directory";
  const fullPath = path ? `${path}/${entry.name}` : entry.name;
  const isSelected = selectedPath === fullPath;

  return (
    <Box>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          pl: `${8 + depth * 20}px`,
          pr: "8px",
          py: "3px",
          cursor: "pointer",
          borderRadius: "4px",
          backgroundColor: isSelected ? "action.selected" : "transparent",
          "&:hover": { backgroundColor: "action.hover" },
          userSelect: "none",
        }}
        onClick={() => {
          if (isDir) {
            setExpanded(!expanded);
          } else {
            onSelect(fullPath);
          }
        }}
      >
        {isDir ? (
          expanded ? (
            <ExpandMoreIcon sx={{ fontSize: 16, color: "text.secondary" }} />
          ) : (
            <ChevronRightIcon sx={{ fontSize: 16, color: "text.secondary" }} />
          )
        ) : (
          <Box sx={{ width: 16 }} />
        )}
        {isDir ? (
          <FolderIcon sx={{ fontSize: 16, color: "warning.main" }} />
        ) : (
          <FileIcon sx={{ fontSize: 16, color: "text.secondary" }} />
        )}
        <Typography
          variant="body2"
          sx={{
            fontSize: "13px",
            fontWeight: isDir ? 500 : 400,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {entry.name}
        </Typography>
      </Box>
      {isDir && expanded && entry.children && (
        <Box>
          {entry.children.map((child) => (
            <TreeNode
              key={child.name}
              entry={child}
              path={fullPath}
              selectedPath={selectedPath}
              onSelect={onSelect}
              depth={depth + 1}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}

const Experiment = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { library = "", id = "" } = useParams<{
    library: string;
    id: string;
  }>();
  const { data: experiment, isLoading, isError } = useExperimentDetail(id);

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);

  const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]);

  const isHtmlFile = useMemo(
    () => selectedFile?.toLowerCase().endsWith(".html") ?? false,
    [selectedFile],
  );

  const isSvgFile = useMemo(
    () => selectedFile?.toLowerCase().endsWith(".svg") ?? false,
    [selectedFile],
  );

  const isImageFile = useMemo(() => {
    if (!selectedFile) return false;
    const ext = selectedFile.toLowerCase().slice(selectedFile.lastIndexOf("."));
    return IMAGE_EXTENSIONS.has(ext);
  }, [selectedFile]);

  const handleFileSelect = useCallback(
    async (path: string) => {
      setSelectedFile(path);
      setFileContent(null);
      setFileLoading(true);

      const ext = path.toLowerCase().slice(path.lastIndexOf("."));
      if (IMAGE_EXTENSIONS.has(ext)) {
        setFileContent("__image__");
        setFileLoading(false);
        return;
      }

      try {
        const result = await fetchExperimentFile(id, path);
        setFileContent(result.content);
      } catch {
        setFileContent("Error loading file.");
      } finally {
        setFileLoading(false);
      }
    },
    [id],
  );

  if (isLoading) {
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "50vh",
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (isError || !experiment) {
    return (
      <Box
        sx={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 2,
          mt: 8,
        }}
      >
        <Typography variant="h6">
          Experiment not found or not yet executed.
        </Typography>
        <Button onClick={() => navigate(`/${library}/experiments`)}>
          Back to Experiments
        </Button>
      </Box>
    );
  }

  return (
    <PageWithTitle
      title={
        <Typography
          variant="h5"
          sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
        >
          {experiment.name}
        </Typography>
      }
    >
      <Box sx={{ height: "calc(100vh - 200px)", overflow: "hidden" }}>
        <PanelGroup orientation="horizontal">
          <Panel defaultSize={400} minSize={200} maxSize={400}>
            <Box sx={{ height: "100%", overflow: "auto", pr: 1 }}>
              <Typography
                variant="subtitle2"
                sx={{ px: 1, py: 1, color: "text.secondary" }}
              >
                Files
              </Typography>
              {experiment.tree.map((entry) => (
                <TreeNode
                  key={entry.name}
                  entry={entry}
                  path=""
                  selectedPath={selectedFile}
                  onSelect={handleFileSelect}
                />
              ))}
            </Box>
          </Panel>

          <PanelResizeHandle
            style={{
              width: 4,
              backgroundColor: "transparent",
              cursor: "col-resize",
              borderLeft: "1px solid var(--mui-palette-divider, #444)",
              transition: "background-color 0.15s",
            }}
            className="experiment-resize-handle"
          />

          <Panel>
            <Box sx={{ height: "100%", overflow: "auto", pl: 2 }}>
              {!selectedFile && (
                <Box
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: "100%",
                  }}
                >
                  <Typography variant="body1" color="text.secondary">
                    Select a file to view its contents
                  </Typography>
                </Box>
              )}
              {selectedFile && fileLoading && (
                <Box sx={{ display: "flex", justifyContent: "center", pt: 4 }}>
                  <CircularProgress size={24} />
                </Box>
              )}
              {selectedFile && !fileLoading && fileContent !== null && (
                <Box sx={{ height: "100%" }}>
                  <Typography
                    variant="caption"
                    sx={{
                      px: 1,
                      py: 0.5,
                      color: "text.secondary",
                      display: "block",
                    }}
                  >
                    {selectedFile}
                  </Typography>
                  {isHtmlFile ? (
                    <iframe
                      srcDoc={fileContent}
                      title={selectedFile}
                      sandbox="allow-scripts allow-same-origin"
                      style={{
                        width: "100%",
                        height: "calc(100% - 30px)",
                        border: "none",
                        borderRadius: 4,
                        backgroundColor: "#fff",
                      }}
                    />
                  ) : isSvgFile ? (
                    <iframe
                      srcDoc={`<!DOCTYPE html><html><head><style>body{margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;background:#fff}svg{max-width:100%;height:auto}</style></head><body>${fileContent}</body></html>`}
                      title={selectedFile}
                      sandbox="allow-same-origin"
                      style={{
                        width: "100%",
                        height: "calc(100% - 30px)",
                        border: "none",
                        borderRadius: 4,
                        backgroundColor: "#fff",
                      }}
                    />
                  ) : isImageFile ? (
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        height: "calc(100% - 30px)",
                        backgroundColor: "#fff",
                        borderRadius: 1,
                        p: 2,
                      }}
                    >
                      <img
                        src={`${API_BASE_URL}/api/experiments/${encodeURIComponent(id)}/file?path=${encodeURIComponent(selectedFile)}`}
                        alt={selectedFile}
                        style={{
                          maxWidth: "100%",
                          maxHeight: "100%",
                          objectFit: "contain",
                        }}
                      />
                    </Box>
                  ) : (
                    <CodeBlock
                      code={fileContent}
                      language={getLanguageFromPath(selectedFile)}
                    />
                  )}
                </Box>
              )}
            </Box>
          </Panel>
        </PanelGroup>
      </Box>
    </PageWithTitle>
  );
};

export default Experiment;
