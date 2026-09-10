import { Fragment } from 'react'
import { Outlet } from 'react-router-dom'

export function RootLayout() {
  return (
    <Fragment>
      <Outlet />
    </Fragment>
  )
}
