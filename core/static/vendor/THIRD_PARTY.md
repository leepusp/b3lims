# Third-party static assets

The Biobank application vendors the following browser assets so the
application can operate without requiring Internet access at runtime.

| Component | Version | License | Local path / note |
| --- | --- | --- | --- |
| Bootstrap | 5.3.2 | MIT | `bootstrap/5.3.2/` |
| Popper Core | 2.11.8 | MIT | Embedded in the Bootstrap bundle |
| Bootstrap Icons | 1.11.1 | MIT | `bootstrap-icons/1.11.1/` |
| Bootstrap Icons | 1.13.1 | MIT | `bootstrap-icons/1.13.1/` |
| FullCalendar | 6.1.10 | MIT | `fullcalendar/6.1.10/` |
| Leaflet | 1.9.4 | BSD-2-Clause | `leaflet/1.9.4/` |
| Quill | 1.3.6 | BSD-3-Clause | `quill/1.3.6/` |
| vis-network | 10.1.2 | Apache-2.0 OR MIT | `vis-network/10.1.2/` |
| Plotly.js | 2.35.2 | MIT | `plotly/2.35.2/` |
| Apache ECharts | 5.5.1 | Apache-2.0 | `echarts/5.5.1/` |
| echarts-maps | 1.1.0 | MIT | `echarts-maps/1.1.0/` |
| Inter | Google Fonts v20 | OFL-1.1 | `inter/google-fonts-v20/` |

Versions are intentionally pinned. Do not replace vendored files with
unversioned CDN URLs.

License and NOTICE files are stored alongside the corresponding vendored
artifacts. The Inter font directory includes its OFL license text.

These files are part of the standalone distribution and must remain with
the vendored assets when the application is packaged or redistributed.
