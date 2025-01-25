import pandas as pd
import plotly.express as px

data = pd.read_sql(
    r"""
    with rtcompare as (
        select 
            titles.netflix_id, 
            titles.title, 
            vendor, 
            rating, 
            count(*) over (partition by titles.netflix_id) ct
        from ratings
        join titles
            on titles.netflix_id = ratings.netflix_id 
        where vendor in ('Google users', 'IMDb', 'Rotten Tomatoes')
            and rating > 0
            and title !~* '\d+\_.*'
    )
    select * from rtcompare
    where ct = 3
    order by 1""",
    "postgresql+psycopg://postgres@localhost:5432",
)


# Create the violin plot
fig = px.violin(
    data,
    x="vendor",
    y="rating",
    color="vendor",  # Add color for better differentiation
    box=True,  # Show box plot inside the violin plot
    points="all",  # Show all data points
    title="Distribution of Ratings by Vendor",
)

# Update layout for better appearance
fig.update_layout(
    xaxis_title="Vendor",
    yaxis_title="Rating",
    template="plotly_dark",
    title_x=0.5,
    font=dict(size=14),
)

# Show the plot
fig.show()
