import argparse
import itertools
import json
import logging
import site
import textwrap
from typing import Any

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from tabulate import tabulate

INDENT_SIZE = 4
REGISTERED_TABLES = {
    "students": [
        "firstName",
        "lastName",
        "email",
        "gender",
        "aidApproved",
        "familyIncome",
    ]
}

VF_FIELDS = ["aidApproved", "familyIncome"]


class Site:
    def __init__(self, url, site_name=None) -> None:
        if site_name:
            self.site_name = site_name

        self.transport = AIOHTTPTransport(url=url)
        self.client = Client(transport=self.transport, fetch_schema_from_transport=True)
        return

    def query(self, table, fields) -> Any:
        query = self.generate_query(table, fields)

        if query:
            result = self.client.execute(query)

        if result:
            return self.postprocess(result)

    def query_aid(self):
        if self.site_name != "postgres":
            return

        query_string = textwrap.dedent(
            """
                query getStudentAid {
                    allStudentAids { 
                        nodes {
                            studentId
                            aidApproved
                            familyIncome
                        }
                    }
                }
                """
        )

        query = gql(query_string)
        result = self.client.execute(query)

        if result:
            rows = result["allStudentAids"]["nodes"]
            records = dict()

            for row in rows:
                id = row["studentId"]
                row.pop("studentId")
                records[id] = row

            return records

    def generate_query(self, table, fields):

        if self.site_name == "sqlite":
            fields_pad = 2
        elif self.site_name == "postgres":
            fields_pad = 3

        fields_string = textwrap.indent(
            "\n".join(["id", *fields]), " " * (fields_pad * INDENT_SIZE)
        )

        if self.site_name == "sqlite":
            query_string = textwrap.dedent(
                """
                query getStudents {{
                    {table} {{ 
                {fields} 
                    }}
                }}
                """
            ).format(
                fields=fields_string,
                table=table,
            )

        elif self.site_name == "postgres":
            table = "all" + table[0].upper() + table[1:]

            query_string = textwrap.dedent(
                """
                query getStudents {{
                    {table} {{
                        nodes {{ 
                {fields} 
                        }}
                    }}
                }}
                """
            ).format(
                fields=fields_string,
                table=table,
            )

        if query_string:
            return gql(query_string)

    def postprocess(self, result):
        try:
            if self.site_name == "sqlite":
                return result["students"]
            elif self.site_name == "postgres":
                return result["allStudents"]["nodes"]

            return result
        except Exception as exc:
            logging.warning(exc_info=exc)


class Middleware:
    def __init__(self, *sites) -> None:
        self.sites = sites

    def query(self, table, fields):
        vf_fields = set(fields) & set(VF_FIELDS)

        result = list(
            filter(
                lambda v: bool,
                list(
                    itertools.chain(
                        *[
                            site.query(
                                table,
                                list(filter(lambda v: v not in VF_FIELDS, fields)),
                            )
                            for site in self.sites
                        ]
                    )
                ),
            )
        )

        if len(vf_fields):
            postgres_site = list(
                filter(lambda v: v.site_name == "postgres", self.sites)
            )[0]

            vf_result = postgres_site.query_aid()

            for row in result:
                rest = vf_result[row["id"]]
                rest_subset = dict((k, rest.get(k)) for k in vf_fields)
                row.update(rest_subset)

        return result


middleware = Middleware(
    Site("http://localhost:8888/graphql", "sqlite"),
    Site("http://localhost:5000/graphql", "postgres"),
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Distributed database simulation with Postgres and SQLite"
    )

    parser.add_argument("-t", "--table", type=str, help="Table name", required=True)
    parser.add_argument(
        "-f", "--field", nargs="+", help="Fields to fetch", required=True
    )

    args = parser.parse_args()

    tables = REGISTERED_TABLES.keys()

    if not args.table in tables:
        print("No such table", args.table)
        exit(1)

    fields = REGISTERED_TABLES.get(args.table)

    if not fields:
        print("Table {} has no registered fields".format(args.table))
        exit(1)

    for field in args.field:
        if not field in fields:
            print("No such field", field)
            exit(1)

    result = middleware.query(
        args.table,
        args.field,
    )

    header = result[0].keys()
    rows = [row.values() for row in result]

    print(tabulate(rows, header))
