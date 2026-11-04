declare module "react-plotly.js" {
  import type { ComponentType, CSSProperties } from "react";
  import type { Config, Data, Layout } from "plotly.js";

  export type PlotParams = {
    data?: Data[];
    layout?: Partial<Layout>;
    config?: Partial<Config>;
    className?: string;
    style?: CSSProperties;
    useResizeHandler?: boolean;
  };

  const Plot: ComponentType<PlotParams>;
  export default Plot;
}

