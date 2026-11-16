import { describe, expect, it } from "vitest";
import { parseCsv } from "@/lib/csv";

describe("parseCsv", () => {
  it("keeps a quote inside an unquoted field as a literal character", () => {
    // A quote in the middle of a cell (inches, a quoted nickname, ...) is not
    // an opening quote — treating it as one used to swallow every following
    // row into that cell and silently drop the rest of the import.
    const rows = parseCsv(
      'date,amount,description\n2024-01-01,100,Adapter 12" screen\n2024-01-02,50,Cable'
    );

    expect(rows).toEqual([
      ["date", "amount", "description"],
      ["2024-01-01", "100", 'Adapter 12" screen'],
      ["2024-01-02", "50", "Cable"],
    ]);
  });

  it("ignores delimiters inside quoted cells when detecting the delimiter", () => {
    // The header's first cell is quoted and contains a comma; the file is
    // semicolon-separated, so counting that comma would pick "," and parse
    // the whole header as one cell.
    const rows = parseCsv('"Date, time";Amount\n01.01.2024, 10:00;100');

    expect(rows).toEqual([
      ["Date, time", "Amount"],
      ["01.01.2024, 10:00", "100"],
    ]);
  });

  it("keeps newlines and escaped quotes inside a quoted field", () => {
    const rows = parseCsv('a,b\n"line 1\nline ""2""",x');

    expect(rows).toEqual([
      ["a", "b"],
      ['line 1\nline "2"', "x"],
    ]);
  });

  it("drops a trailing blank line instead of adding an empty row", () => {
    expect(parseCsv("a,b\n1,2\n")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });
});
