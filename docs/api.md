***

# File Management Endpoint (`/files`)

This endpoint provides file management capabilities, allowing clients to upload, retrieve, and manage files through various HTTP methods. `http_files_api` must be set to `True` in pyrobusta.env to enable this API.

## Summary

| Method   | Path                 | Description |
| :------- | :------------------- | :---------- |
| `GET`    | `/files/{path}`      | Lists or retrieves metadata about files. |
| `PUT`    | `/files/{file path}` | Uploads or overwrites a file at the specified path. |
| `POST`   | `/files`             | Uploads multiple files in multipart/form-data. |
| `DELETE` | `/files/{file path}` | Delete a file at the specified path. |

---

## Endpoint Details

### 1. File Retrieval/Listing (`GET /files/{path}`)

This endpoint allows general file system interaction, enabling operations such as listing directory contents and retrieving metadata as well as downloading files.

*   **Method:** `GET`
*   **Path:** `/files/{path}`
*   **Success Response:** 200 OK.

### 2. File Upload / Overwrite (`PUT /files/{file path}`)

This method is used to upload a file or overwrite an existing file at a specific path.
The upload path is restricted to /www/user_data.

*   **Method:** `PUT`
*   **Path:** `/files/{file path}`
*   **Body:** Raw file content (e.g., binary data).
*   **Success Response:** 201 Created.
*   **Notes:** `transfer-encoding: chunked` is supported.

### 3. File Upload (`POST /files`)

This method handles general file uploads, designed for uploading multiple files with per-file chunking supported. Only multipart/form-data is accepted as a content type.

The upload path is restricted to /www/user_data, however, content-disposition headers only have to specify the file name, /www/user_data is prepended by default.

`http_multipart` must be set to `True` in the configuration to use this endpoint.

*   **Method:** `POST`
*   **Path:** `/files`
*   **Body:** File content encapsulated in multipart/form-data.
*   **Success Response:** 201 Created.

### 4. File Delete (`DELETE /files/{file path}`)

This method is used to delete a file at a specific path.
The path is restricted to /www/user_data.

*   **Method:** `PUT`
*   **Path:** `/files/{file path}`
*   **Success Response:** 204 No Content.
