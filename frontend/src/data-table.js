import React from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from "@mui/material";

export const DataTable = ({ data }) => {
  if (!data || data.length === 0) {
    return <p>No data to display.</p>;
  }

  // Automatically get all column headers from the first item in the data array.
  const headers = Object.keys(data[0]);

  return (
    <TableContainer
      component={Paper}
      sx={{ mt: 2, maxHeight: 440, overflowX: "auto", width: "100%" }}
    >
      <Table
        stickyHeader
        aria-label="integration data table"
        sx={{ minWidth: 650 }}
      >
        <TableHead>
          <TableRow>
            {headers.map((header) => (
              <TableCell
                key={header}
                sx={{
                  fontWeight: "bold",
                  minWidth: 120,
                  maxWidth: 200,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {header.replace("_", " ").toUpperCase()}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((item) => (
            <TableRow key={item.id}>
              {headers.map((header) => (
                <TableCell
                  key={`${item.id}-${header}`}
                  sx={{
                    minWidth: 120,
                    maxWidth: 200,
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    fontSize: "0.875rem",
                  }}
                  title={
                    typeof item[header] === "boolean"
                      ? String(item[header])
                      : item[header]
                  }
                >
                  {/* We convert boolean values to strings to display them */}
                  {typeof item[header] === "boolean"
                    ? String(item[header])
                    : item[header]}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
};
