# Revision 3 measurement summary

Runs analysed: 80

## Completed repetitions

| scenario | Vapor | Spring Boot, Tomcat 200 | Spring Boot, Tomcat 64 | Spring Boot, virtual threads |
|---|---|---|---|---|
| load | 5 | 5 | 5 | 5 |
| stress | 5 | 5 | 5 | 5 |
| spike | 5 | 5 | 5 | 5 |
| soak | 5 | 5 | 5 | 5 |

## Tail latency, client measured, milliseconds

| scenario | config | n | median P95 | IQR | 95% CI of median |
|---|---|---|---|---|---|
| load | Vapor | 5 | 1199.2 | 96.7 | [1096.0, 1288.4] |
| load | Spring Boot, Tomcat 200 | 5 | 2587.8 | 6.4 | [2496.5, 2689.1] |
| load | Spring Boot, Tomcat 64 | 5 | 2588.5 | 9.5 | [2584.4, 2605.9] |
| load | Spring Boot, virtual threads | 5 | 836.3 | 190.0 | [767.8, 1066.1] |
| stress | Vapor | 5 | 23206.3 | 396.7 | [21607.9, 24198.0] |
| stress | Spring Boot, Tomcat 200 | 5 | 33312.8 | 247.5 | [33078.8, 34432.2] |
| stress | Spring Boot, Tomcat 64 | 5 | 28295.2 | 602.7 | [27802.5, 31296.4] |
| stress | Spring Boot, virtual threads | 5 | 21990.3 | 902.9 | [19681.5, 22411.1] |
| spike | Vapor | 5 | 14.7 | 1.8 | [13.5, 15.9] |
| spike | Spring Boot, Tomcat 200 | 5 | 15.3 | 1.5 | [14.4, 18.0] |
| spike | Spring Boot, Tomcat 64 | 5 | 14.8 | 1.4 | [14.4, 16.4] |
| spike | Spring Boot, virtual threads | 5 | 13.8 | 0.4 | [11.4, 14.7] |
| soak | Vapor | 5 | 98.4 | 11.3 | [89.8, 124.6] |
| soak | Spring Boot, Tomcat 200 | 5 | 122.6 | 40.0 | [110.1, 177.6] |
| soak | Spring Boot, Tomcat 64 | 5 | 115.5 | 8.2 | [104.4, 133.0] |
| soak | Spring Boot, virtual threads | 5 | 264.7 | 193.6 | [253.9, 455.5] |

## Load generator cost on the shared host

| scenario | config | mean k6 CPU, percent of one core | peak | peak RSS MB |
|---|---|---|---|---|
| load | Vapor | 3 | 4 | 80 |
| load | Spring Boot, Tomcat 200 | 2 | 4 | 77 |
| load | Spring Boot, Tomcat 64 | 2 | 4 | 77 |
| load | Spring Boot, virtual threads | 3 | 4 | 78 |
| stress | Vapor | 2 | 7 | 248 |
| stress | Spring Boot, Tomcat 200 | 2 | 7 | 240 |
| stress | Spring Boot, Tomcat 64 | 2 | 7 | 246 |
| stress | Spring Boot, virtual threads | 2 | 9 | 247 |
| spike | Vapor | 13 | 27 | 122 |
| spike | Spring Boot, Tomcat 200 | 14 | 29 | 123 |
| spike | Spring Boot, Tomcat 64 | 13 | 28 | 124 |
| spike | Spring Boot, virtual threads | 14 | 29 | 122 |
| soak | Vapor | 2 | 2 | 51 |
| soak | Spring Boot, Tomcat 200 | 2 | 2 | 52 |
| soak | Spring Boot, Tomcat 64 | 2 | 2 | 50 |
| soak | Spring Boot, virtual threads | 2 | 2 | 51 |
