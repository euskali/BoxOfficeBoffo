// SQL lives in plain .sql files so the browser (DuckDB-WASM) and the Python tests run the same text.
import helloSql from './hello.sql?raw'

export { helloSql }
