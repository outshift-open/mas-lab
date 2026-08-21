//  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
//  SPDX-License-Identifier: Apache-2.0
import { Box, Typography, useTheme } from "@mui/material";
import { useNavigate, useParams } from "react-router";
import { PageWithTitle } from "@/components";
import {
  IoCRunConfigForm,
  type IoCRunConfig,
} from "@/components/IoCRunConfigForm/IoCRunConfigForm";
import { submitIocRun } from "@/api/apiCalls";

const NewIoCRun = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { library = "" } = useParams<{ library: string }>();

  const handleSubmit = async (config: IoCRunConfig) => {
    await submitIocRun({
      app: config.app,
      overlays: config.selectedOverlays.map((o) => o.overlayId),
      query: config.query || undefined,
      reps: config.reps,
    });
    navigate(`/${library}/ioc-motivation`);
  };

  const handleCancel = () => {
    navigate(`/${library}/ioc-motivation`);
  };

  return (
    <Box>
      <PageWithTitle
        title={
          <Typography
            variant="h5"
            sx={{ color: theme.palette.vars.interactivePrimaryDefaultDefault }}
          >
            New IoC Run
          </Typography>
        }
      >
        <IoCRunConfigForm
          library={library}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
        />
      </PageWithTitle>
    </Box>
  );
};

export default NewIoCRun;
