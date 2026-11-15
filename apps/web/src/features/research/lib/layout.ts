/**
 * Layout-shift guard for panels whose content arrives asynchronously (CLS was 0.33–0.52 on
 * /benchmarks and 0.32 on /contingency): while a panel shows a loading skeleton (`aria-busy`), its
 * body reserves one viewport height, so panels below start off-screen and their displacement as
 * artifacts arrive is not a visible shift. The reservation drops as soon as the content is in.
 */
export const RESERVE_WHILE_LOADING = 'has-[[aria-busy=true]]:min-h-svh'
