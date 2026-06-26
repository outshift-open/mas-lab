//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { PageWithTitle, DatasetEditor } from "@/components";
import {
  Alert,
  Box,
  CircularProgress,
  Stack,
  TextField,
  Typography,
  useTheme,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from "@mui/material";
import { useNavigate, useParams } from "react-router";
import { useEffect, useMemo, useState } from "react";
import {
  useDatasetDetail,
  useUpdateDataset,
  useCreateDataset,
  useDeleteDataset,
} from "@/api/apiCalls";
import { useQueryClient } from "@tanstack/react-query";

const Dataset = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { library = "", id } = useParams<{
    library: string;
    id: string;
  }>();
  const queryClient = useQueryClient();

  const isNew = !id;

  const { data: dataset, isLoading, isError } = useDatasetDetail(library, isNew ? "" : id);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saveDescription, setSaveDescription] = useState("");
  const [saveAlert, setSaveAlert] = useState<{
    severity: "success" | "error";
    message: string;
  } | null>(null);

  const emptyDatasetContent = JSON.stringify({ items: [] }, null, 2);

  const initialContent = useMemo(() => {
    if (isNew) return emptyDatasetContent;
    if (!dataset?.content) return "";
    try {
      return JSON.stringify(JSON.parse(dataset.content), null, 2);
    } catch {
      return dataset.content;
    }
  }, [dataset, isNew]);

  const [editedContent, setEditedContent] = useState<string | null>(null);
  const currentContent = editedContent ?? initialContent;

  const saveMutation = useUpdateDataset(library, id ?? "");
  const createMutation = useCreateDataset(library);

  const openSaveDialog = () => {
    setSaveName(isNew ? "" : (dataset?.name ?? id ?? ""));
    setSaveDescription("");
    try {
      const parsed = JSON.parse(currentContent);
      if (parsed.description) setSaveDescription(parsed.description);
    } catch { /* ignore */ }
    setSaveDialogOpen(true);
  };

  const [lastSavedName, setLastSavedName] = useState("");

  const handleSave = () => {
    setSaveAlert(null);
    setSaveDialogOpen(false);
    setLastSavedName(saveName);
    let contentToSave = currentContent;
    try {
      const parsed = JSON.parse(currentContent);
      parsed.name = saveName;
      parsed.description = saveDescription;
      contentToSave = JSON.stringify(parsed, null, 2);
    } catch { /* send as-is */ }

    if (isNew) {
      createMutation.mutate({ name: saveName, content: contentToSave });
    } else {
      saveMutation.mutate({ name: saveName, content: contentToSave });
    }
  };

  useEffect(() => {
    if (saveMutation.isSuccess) {
      queryClient.invalidateQueries({ queryKey: ["datasets-list", library] });
      if (lastSavedName && lastSavedName !== (id ?? "")) {
        navigate(`/${library}/datasets/${encodeURIComponent(lastSavedName)}`, { replace: true });
      } else {
        queryClient.invalidateQueries({ queryKey: ["dataset", library, id ?? ""] });
        setEditedContent(null);
        setSaveAlert({
          severity: "success",
          message: "Dataset saved successfully",
        });
      }
    }
    if (saveMutation.isError) {
      const err = saveMutation.error;
      setSaveAlert({
        severity: "error",
        message: err instanceof Error ? err.message : "Failed to save dataset",
      });
    }
  }, [saveMutation.isSuccess, saveMutation.isError]);

  useEffect(() => {
    if (createMutation.isSuccess) {
      queryClient.invalidateQueries({ queryKey: ["datasets-list", library] });
      setSaveAlert({ severity: "success", message: "Dataset created successfully" });
      navigate(`/${library}/datasets/${encodeURIComponent(lastSavedName)}`, { replace: true });
    }
    if (createMutation.isError) {
      const err = createMutation.error;
      setSaveAlert({
        severity: "error",
        message: err instanceof Error ? err.message : "Failed to create dataset",
      });
    }
  }, [createMutation.isSuccess, createMutation.isError]);

  const deleteMutation = useDeleteDataset(library, id ?? "");

  useEffect(() => {
    if (deleteMutation.isSuccess) {
      queryClient.invalidateQueries({ queryKey: ["datasets-list", library] });
      navigate(`/${library}/datasets`, { replace: true });
    }
    if (deleteMutation.isError) {
      setDeleteDialogOpen(false);
    }
  }, [deleteMutation.isSuccess, deleteMutation.isError]);

  if (!isNew && isLoading) {
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

  if (!isNew && (isError || !dataset)) {
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
        <Typography variant="h6">Dataset not found</Typography>
        <Typography variant="body2" sx={{ color: "text.secondary" }}>
          The dataset &quot;{id ?? ""}&quot; does not exist or has been deleted.
        </Typography>
        <Button
          variant="primary"
          onClick={() => navigate(`/${library}/datasets`)}
        >
          Back to Datasets
        </Button>
      </Box>
    );
  }

  return (
    <PageWithTitle
      title={
        <Stack
          direction="row"
          sx={{
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
          }}
        >
          <Typography
            variant="h5"
            sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
          >
            {isNew ? "New Dataset" : dataset!.name}
          </Typography>
          <Stack direction="row" sx={{ gap: 1 }}>
            <Button
              variant="primary"
              onClick={openSaveDialog}
              disabled={saveMutation.isPending || createMutation.isPending}
            >
              {saveMutation.isPending || createMutation.isPending ? "Saving..." : "Save"}
            </Button>
            {!isNew && (
              <Button
                variant="primary"
                color="negative"
                onClick={() => setDeleteDialogOpen(true)}
              >
                Delete
              </Button>
            )}
          </Stack>
        </Stack>
      }
    >
      {saveAlert && (
        <Alert
          severity={saveAlert.severity}
          onClose={() => setSaveAlert(null)}
          sx={{
            whiteSpace: "pre-wrap",
            position: "absolute",
            top: 0,
            right: 0,
            zIndex: 1000,
          }}
        >
          {saveAlert.message}
        </Alert>
      )}
      <DatasetEditor content={currentContent} onChange={setEditedContent} />

      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)}>
        <DialogTitle>Save Dataset</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField
            label="Name"
            variant="standard"
            fullWidth
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
          />
          <TextField
            label="Description"
            variant="standard"
            fullWidth
            multiline
            minRows={2}
            value={saveDescription}
            onChange={(e) => setSaveDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveDialogOpen(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} disabled={!saveName.trim()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
      >
        <DialogTitle>Delete Dataset</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete &quot;{dataset?.name}&quot;? This
            action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setDeleteDialogOpen(false)}
            disabled={deleteMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            color="negative"
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogActions>
      </Dialog>
    </PageWithTitle>
  );
};

export default Dataset;
