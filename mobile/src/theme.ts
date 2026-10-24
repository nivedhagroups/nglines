export const colors = {
  ink: "#172522",
  muted: "#64736D",
  paper: "#F7F8F4",
  surface: "#FFFFFF",
  line: "#DCE4DE",
  forest: "#176B52",
  forestDark: "#104B3B",
  lime: "#D5ED82",
  amber: "#E4A33B",
  coral: "#C8533B",
  sky: "#5E93A3",
  error: "#B83E35",
  success: "#247451",
};

export const spacing = { xs: 4, sm: 8, md: 14, lg: 20, xl: 28, xxl: 36 } as const;

export const typography = {
  title: { fontSize: 27, fontWeight: "700" as const, color: colors.ink },
  heading: { fontSize: 18, fontWeight: "700" as const, color: colors.ink },
  body: { fontSize: 15, color: colors.ink },
  caption: { fontSize: 12, color: colors.muted },
};